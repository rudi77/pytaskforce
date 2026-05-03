# Integrating Taskforce into Your Application

**Audience:** Developers building a Python (or polyglot) application that needs
agentic capabilities and wants to embed or call Taskforce.

This guide covers the **three supported integration modes**, the **public
API surface** (`taskforce.host`) you should use for any of them, and
end-to-end recipes for the most common scenarios.

> **Are you connecting Taskforce to Telegram, Teams, Slack, etc.?**
> Those are *channels* (handled by the Communication Gateway) — see
> [External Integrations](integrations.md). This guide is about
> **embedding the Taskforce framework itself** into a host application.

---

## 1. Pick an Integration Mode

| Mode | Latency | Process boundary | Streaming | Best for |
|------|---------|------------------|-----------|----------|
| **A. Library (in-process)** | <1 ms | Same process | Native async iterators | Single-service Python apps with low latency budgets, full control over agent lifecycle. |
| **B. CLI / Subprocess** | 50–200 ms (cold start) | Subprocess | Line-by-line stdout | Build pipelines, CI scripts, ad-hoc agent runs. |
| **C. Webservice (sidecar / embedded)** | 1–10 ms (HTTP) | Separate container or mounted FastAPI | SSE | Polyglot stacks, multi-service deployments, multi-tenant SaaS, separate scaling. |

**Decision shortcut:**
- **One Python service, full streaming, you own the lifecycle?** → Mode A.
- **Bash script, GitHub Action, eval harness?** → Mode B.
- **Anything in production with a frontend, multiple services, or a non-Python stack?** → Mode C.

You can mix modes: e.g. run Taskforce as a sidecar (Mode C) and *also*
import `taskforce.host.register_tool` in-process from a small Python
helper that registers your custom tools on startup (Mode A used as a
configuration step for Mode C).

---

## 2. The Public API: `taskforce.host`

**Everything in `taskforce.host` is part of the stable contract.** Anything else (`taskforce.infrastructure.*`, `taskforce.application.*`, `taskforce.api.routes.*`) is internal and may change between minor versions.

```python
from taskforce.host import (
    # Tool / profile / skill registration
    register_tool,                  # idempotent
    unregister_tool,
    is_tool_registered,
    register_profile_dir,           # add directory to ProfileLoader search path
    register_skill_dir,             # add directory to skill discovery
    # FastAPI embedding
    mount_routes,                   # mount a subset of taskforce routers
    create_embedded_app,            # build a FastAPI app with a router subset
    available_routers,              # enumerate router names
    # Infrastructure overrides (advanced; multi-tenant)
    set_agent_registry_override,
    set_state_manager_override,
    set_gateway_components_override,
    clear_infrastructure_overrides,
)
```

If you ever find yourself writing `from taskforce.infrastructure...` or
`from taskforce.application...` in a host application, **stop and check
whether the symbol is available via `taskforce.host`**. If it isn't, file
an issue rather than reaching into a private module.

The host integration design is documented in [ADR-023](adr/adr-023-host-integration-api.md).

---

## 3. Installation

Taskforce is **not on PyPI yet** (subject to change). Install from Git or a
local checkout:

```bash
# Latest stable
uv pip install "taskforce @ git+https://github.com/rudi77/pytaskforce@main"

# Pin a specific version
uv pip install "taskforce @ git+https://github.com/rudi77/pytaskforce@v0.1.49"

# Local development (lets you patch taskforce alongside your app)
uv pip install -e /path/to/pytaskforce
uv pip install -e /path/to/pytaskforce/cli      # adds the `taskforce` CLI binary
```

For Mode C (webservice) you almost certainly want the CLI package —
that's where `taskforce serve` lives.

Optional dependency groups (only install what you need):
```bash
uv pip install "taskforce[browser]"   # Playwright headless browser tool
uv pip install "taskforce[rag]"       # Azure AI Search
uv pip install "taskforce[office]"    # docx/pptx/excel tools
uv pip install "taskforce[acp]"       # Agent Communication Protocol
```

Set environment variables for your LLM provider (Azure OpenAI shown):
```bash
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-10-21
```

---

## 4. Mode A — Library (in-process)

You import `AgentFactory` directly and own the agent lifecycle.

### 4.1 Minimal example

```python
import asyncio
from taskforce.application.factory import AgentFactory

async def main():
    factory = AgentFactory()                 # cache once at startup
    agent = await factory.create_agent(
        system_prompt="You are a helpful assistant.",
        tools=["python", "file_read", "file_write"],
        max_steps=20,
    )
    try:
        result = await agent.execute(
            mission="Compute the SHA-256 of the string 'taskforce'.",
            session_id="demo-1",
        )
        print(result.final_answer)
    finally:
        await agent.close()                  # MUST — releases MCP / tracker

asyncio.run(main())
```

### 4.2 Lifecycle invariants

These are **load-bearing** — most production bugs in library mode come
from violating one of these:

* **`AgentFactory` is the cache point.** It owns the LiteLLM connection
  pool, tool registry, ProfileLoader. Build it **once** at startup
  (FastAPI lifespan, Django apps.py, asyncio main), reuse it for every
  request. Do NOT instantiate per request.
* **One `Agent` per mission.** The agent's message history initialises
  on each `execute()`. Two parallel chats sharing the same agent
  instance corrupt each other's context. Spawn a fresh agent per
  mission/conversation.
* **Always `await agent.close()`** in a `finally` block. Otherwise MCP
  server connections and the runtime tracker leak.

Pattern for a FastAPI host:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from taskforce.application.factory import AgentFactory

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.tf_factory = AgentFactory()    # cached singleton
    yield
    # nothing to close on the factory itself

app = FastAPI(lifespan=lifespan)

@app.post("/chat")
async def chat(req: ChatRequest):
    agent = await app.state.tf_factory.create_agent(profile="my-agent")
    try:
        return await agent.execute(mission=req.text, session_id=req.session_id)
    finally:
        await agent.close()
```

### 4.3 Streaming responses

`agent.execute_stream()` yields `StreamEvent`s — useful for sending
tokens to a WebSocket client:

```python
async for event in agent.execute_stream(mission="...", session_id="..."):
    etype = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
    if etype == "llm_token":
        await websocket.send_json({"type": "token", "content": event.data["content"]})
    elif etype == "tool_call":
        await websocket.send_json({"type": "tool", "name": event.data["tool_name"]})
    elif etype == "complete":
        await websocket.send_json({"type": "done", "content": event.data["final_message"]})
```

### 4.4 Registering custom tools / profiles / skills

Do this **once** before the first `create_agent()` call, ideally in your
app's startup hook:

```python
from taskforce.host import register_tool, register_profile_dir, register_skill_dir

def configure_taskforce():
    register_tool(
        name="search_inventory",
        tool_type="SearchInventoryTool",
        module="myapp.tools.search_inventory",
    )
    register_profile_dir("./agents")          # finds <name>.yaml or <name>.agent.md
    register_skill_dir("./skills")            # finds <name>/SKILL.md
```

All three calls are **idempotent** — safe to call from `__init__.py`
that gets imported multiple times under uvicorn `--reload` or in tests.

Tool implementation (`myapp/tools/search_inventory.py`):
```python
from taskforce.infrastructure.tools.base_tool import BaseTool

class SearchInventoryTool(BaseTool):
    tool_name = "search_inventory"
    tool_description = "Search the product inventory by SKU or name."
    tool_parameters_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    async def _execute(self, **params) -> dict:
        results = await self.db.search(params["query"])
        return {"matches": results, "success": True}
```

---

## 5. Mode B — CLI / Subprocess

Use this when something else (a script, CI job, or a non-Python service)
just needs to call an agent and read the result.

### 5.1 One-shot mission

```bash
taskforce run mission "Summarize the latest sales report" --profile analyst
```

### 5.2 Streaming mode

```bash
taskforce run mission "Refactor src/api.py" --profile coder --stream
```

### 5.3 Calling from a subprocess

```python
import subprocess, json
result = subprocess.run(
    ["taskforce", "run", "mission", "Generate weekly report", "--profile", "reporter", "--json"],
    capture_output=True, text=True, check=True,
)
payload = json.loads(result.stdout)
```

### 5.4 Calling from a non-Python service

Wrap the CLI in your language's subprocess primitive (Node `child_process.spawn`,
Go `exec.Command`, etc.). For long-running interactive use prefer Mode C.

---

## 6. Mode C — Webservice

Two flavours: **sidecar** (Taskforce in its own process / container) and
**embedded** (selected Taskforce routers mounted on your existing FastAPI app).

### 6.1 Sidecar — `taskforce serve`

The simplest production deployment. One command per sidecar instance:

```bash
taskforce serve --host 0.0.0.0 --port 8070 --workers 4 --log-level info
```

Defaults: `--host 127.0.0.1` (network exposure must be opt-in), `--workers 1`,
`--log-level info`, `--app taskforce.api.server:app`.

#### docker-compose snippet

```yaml
services:
  taskforce:
    image: ghcr.io/your-org/taskforce:latest   # or build locally
    command: ["taskforce", "serve", "--host", "0.0.0.0", "--port", "8070"]
    environment:
      AZURE_OPENAI_API_KEY: ${AZURE_OPENAI_API_KEY}
      AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}    # optional
      TASKFORCE_PROFILE: my-agent
    volumes:
      - ./agents:/profiles                          # your custom profiles
      - ./skills:/skills                            # your custom skills
      - taskforce_data:/app/.taskforce              # persistent state
    ports: ["8070:8070"]

  myapp-backend:
    image: my-org/myapp-backend:latest
    depends_on: [taskforce]
    environment:
      TASKFORCE_URL: http://taskforce:8070

volumes:
  taskforce_data:
```

The sidecar exposes `/docs` (OpenAPI/Swagger), `/health`, and these
endpoints under `/api/v1/`:

| Path | Use |
|------|-----|
| `POST /execute` | Run a mission, get the final result. |
| `POST /execute/stream` | Run a mission, stream events as Server-Sent Events. |
| `POST /gateway/{channel}/messages` | Send a normalized inbound message. |
| `POST /gateway/{channel}/webhook` | Forward a raw provider webhook (Telegram, Teams). |
| `POST /gateway/notify` | Push a proactive notification to a registered recipient. |
| `GET  /gateway/channels` | List configured channels. |
| `GET  /skills`, `POST /skills/{name}/run` | Discover and invoke skills. |
| `GET  /profiles`, `GET /profiles/{name}` | Discover and inspect profiles. |
| `GET  /tools` | List available tools. |
| `POST /conversations`, `GET /conversations/{id}` | Persistent conversations (ADR-016). |

#### Calling the sidecar from your host app

```python
import httpx

async with httpx.AsyncClient(base_url="http://taskforce:8070", timeout=300) as client:
    # Synchronous mission
    resp = await client.post("/api/v1/gateway/web/messages", json={
        "conversation_id": f"web-{user_id}",
        "message": user_text,
        "sender_id": str(user_id),
        "profile": "my-agent",
    })
    reply = resp.json()["reply"]

    # Streaming mission (SSE)
    async with client.stream("POST", "/api/v1/execute/stream", json={
        "mission": user_text,
        "profile": "my-agent",
        "session_id": f"web-{user_id}",
    }) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                # forward to your WebSocket / SSE client
```

#### Registering custom tools in the sidecar

The sidecar runs in its own container, so your tool implementations
must be importable inside that container. Two approaches:

1. **Build a downstream image** that adds your tools:
   ```dockerfile
   FROM ghcr.io/your-org/taskforce:latest
   COPY ./mytools /app/mytools
   ENV PYTHONPATH=/app:/app/mytools
   COPY ./mytools/_register.py /app/.taskforce/startup/_register.py
   ```
   `_register.py` calls `register_tool(...)` for each custom tool.
   Use a startup hook (FastAPI `lifespan` or an entry point) to import it.

2. **Ship your tools as a pip package** with a Taskforce plugin entry
   point (`taskforce.plugins`). The sidecar's `load_all_plugins()` will
   discover and register it automatically. This is the cleanest path if
   your tools are reusable across projects.

#### Telegram via the sidecar

The Gateway already includes a Telegram inbound adapter and outbound
sender. Set `TELEGRAM_BOT_TOKEN` and tell Telegram where to deliver
updates — **once**:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
     -d "url=https://your-public-domain/api/v1/gateway/telegram/webhook?profile=my-agent"
```

Or, if you can't expose the sidecar publicly, run the long-poll loop
inside the sidecar by setting `TELEGRAM_POLL_ENABLED=1` (no webhook
needed; useful in dev).

### 6.2 Embedded — mount Taskforce routes on your existing FastAPI app

Use this when you want a single FastAPI process serving both your app
and Taskforce endpoints (cheaper than a sidecar, gives you direct
access to in-process state).

```python
from fastapi import FastAPI
from taskforce.host import (
    mount_routes,
    register_profile_dir,
    register_skill_dir,
    register_tool,
)

app = FastAPI(title="My App")

# Your own routes
app.include_router(my_router)

# Taskforce setup — same calls as Mode A
register_profile_dir("./agents")
register_skill_dir("./skills")
register_tool("search_inventory", "SearchInventoryTool", "myapp.tools.search_inventory")

# Mount only the routers you actually use
mount_routes(
    app,
    prefix="/agent",                                       # custom prefix
    include=["gateway", "execution", "skills", "conversations", "health"],
)
```

`mount_routes` is **idempotent** (safe under uvicorn `--reload`). The
list of available router names:

```python
from taskforce.host import available_routers
print(available_routers())
# ['acp', 'agent_deployments', 'agent_templates', 'agents', 'analytics',
#  'conversations', 'evals', 'execution', 'files', 'gateway', 'health',
#  'llm', 'mcp', 'memory', 'planning_strategies', 'profiles', 'runs',
#  'skills', 'tools', 'ui', 'workflows']
```

`health` and `acp` are mounted at the app root (their public URLs
aren't under `/api/v1`); everything else honours the `prefix` argument.

#### Alternative: `create_embedded_app` for a sub-app

If you'd rather isolate Taskforce in a sub-application that you mount:

```python
from taskforce.host import create_embedded_app

tf_app = create_embedded_app(
    title="Taskforce (embedded)",
    include=["gateway", "execution", "skills"],
    prefix="/api/v1",
)
app.mount("/agent", tf_app)
# → /agent/api/v1/gateway/..., /agent/docs, /agent/openapi.json
```

This gives you Taskforce its own OpenAPI spec separate from your host app.

---

## 7. Common tasks

### 7.1 Define a custom profile

A profile is a YAML file (`<name>.yaml`) or an Agent-MD file
(`<name>.agent.md`) in any directory you've registered with
`register_profile_dir()`.

Minimal `agents/sales_assistant.yaml`:
```yaml
profile: sales_assistant

agent:
  planning_strategy: native_react
  max_steps: 20

tools: [python, web_search, search_inventory, llm]

system_prompt: |
  You are a sales assistant. When asked about products, use search_inventory.
  When you need market data, use web_search. Always show prices in the user's
  currency, converting via the python tool.
```

Reference it from any mode:
```python
agent = await factory.create_agent(config="sales_assistant")
```
```bash
taskforce run mission "Find me a printer under 200 EUR" --profile sales_assistant
```
```bash
curl -X POST http://taskforce:8070/api/v1/gateway/web/messages \
  -d '{"conversation_id":"u-42","message":"Find me a printer","profile":"sales_assistant"}'
```

The agent-MD format ([docs/agent-config-format.md](agent-config-format.md))
adds Markdown-frontmatter and `extends:` preset references — use it when
your profile has a substantial system prompt.

### 7.2 Define a custom skill

A skill is a directory with a `SKILL.md` file. Three skill types
([docs/features/skills.md](features/skills.md)):

* `context` — instructions injected into the system prompt when activated.
* `prompt` — `/skill-name [args]` becomes a templated prompt with `$ARGUMENTS`.
* `agent` — `/skill-name` switches to a different agent config.

Minimal `skills/quote/SKILL.md`:
```markdown
---
name: quote
description: Generate a sales quote from a customer description.
type: prompt
slash_name: quote
---

You are creating a sales quote. The user described their needs as follows:

$ARGUMENTS

Use the search_inventory tool to find matching products. Use the python
tool for price calculations including 19% VAT. Output a clean summary
with line items, subtotal, VAT, and total.
```

After `register_skill_dir("./skills")` your users can invoke:
```
/quote 5 printers, 2 scanners, color preferred
```
in chat (Telegram, Web, CLI), or your code can:
```python
from taskforce.application.skill_service import get_skill_service
skill = get_skill_service().get_skill("quote")
prompt = get_skill_service().prepare_skill_prompt(skill, "5 printers, 2 scanners")
```

### 7.3 Add a custom communication channel

The Gateway ships Telegram and Teams. To add (e.g.) Slack you implement
two protocols and inject the channel:

```python
from taskforce.core.interfaces.gateway import (
    InboundAdapterProtocol,
    OutboundSenderProtocol,
)

class SlackInboundAdapter:                       # implements InboundAdapterProtocol
    def verify_signature(self, raw_body, headers): ...
    def extract_message(self, raw_payload): ...

class SlackOutboundSender:                       # implements OutboundSenderProtocol
    async def send(self, recipient_id: str, message: str, metadata: dict | None): ...
```

Inject them via the gateway-components override:
```python
from taskforce.host import set_gateway_components_override
from taskforce.infrastructure.communication.gateway_registry import build_gateway_components

def my_gateway_provider(work_dir: str):
    return build_gateway_components(
        work_dir=work_dir,
        extra_senders={"slack": SlackOutboundSender(...)},
        extra_adapters={"slack": SlackInboundAdapter(...)},
    )

set_gateway_components_override(my_gateway_provider)
```

Now `POST /api/v1/gateway/slack/webhook` works.

### 7.4 Persistent conversations across calls

Use the `/api/v1/conversations` endpoints (ADR-016) when you want the
agent to remember previous turns automatically:

```python
# 1. Create conversation
resp = await client.post("/api/v1/conversations", json={"profile": "sales_assistant"})
conv_id = resp.json()["conversation_id"]

# 2. Send messages — gateway resolves session, restores history
for turn in user_messages:
    await client.post(f"/api/v1/conversations/{conv_id}/messages", json={"message": turn})
```

In library mode, use `application.conversation_manager.ConversationManager`.

### 7.5 Multi-tenancy

For SaaS use cases see [ADR-022](adr/adr-022-multi-tenant-enterprise-runtime.md)
and the `taskforce-enterprise` plugin. The integration seam is the
override-hook trio re-exported from `taskforce.host`:
```python
set_agent_registry_override(...)
set_state_manager_override(...)
set_gateway_components_override(...)
```
Plus `taskforce-enterprise` adds an `IdentityProviderProtocol` and
`PolicyEngineProtocol` for RBAC.

---

## 8. Production checklist

| Concern | What to do |
|---------|-----------|
| **Scaling** | Sidecar mode: increase `--workers`. Each worker holds its own `AgentFactory`. State is shared via the `TASKFORCE_WORK_DIR` volume (file-based) or PostgreSQL (`taskforce[postgres]`). |
| **Persistence** | For production use PostgreSQL: `uv pip install "taskforce[postgres]"`, set `DATABASE_URL`, and use the postgres state manager. File-based persistence is fine for dev. |
| **Observability** | Install `taskforce[tracing]` for Phoenix/OTEL. Logs land in `${TASKFORCE_LOG_DIR}/api.log` (default: `.taskforce/logs/api.log`). Token analytics in `.taskforce/analytics.db`. |
| **Authentication** | The standalone `taskforce serve` has **no auth** — front it with a reverse proxy (Caddy / Traefik / nginx) doing JWT validation, or use the embedded mode and put your own auth middleware on the host FastAPI. For full RBAC, `taskforce-enterprise`. |
| **Rate limiting** | None built in. Use the reverse proxy or your host app's middleware. |
| **CORS** | `taskforce serve` reads `CORS_ORIGINS` env var (comma-separated). Default `*` is permissive — set explicit origins in production. |
| **Secrets** | Pass via env vars, not in profiles. Profile YAMLs should not contain API keys. |
| **Health checks** | Sidecar exposes `GET /health`. Readiness — same endpoint, returns `{"status":"healthy",...}`. |
| **Backups** | `${TASKFORCE_WORK_DIR}` (default `.taskforce/`) holds conversations, memory, gateway sessions, scheduled jobs, runtime state. Back this up. With Postgres, your DB backups cover it. |
| **Updates** | Pin Taskforce to a tagged version in your `requirements.txt` / `pyproject.toml`. Test against the new version in a staging container before bumping. |

---

## 9. Migration from direct framework imports

If your code reaches into private modules, swap to the public API:

| Before | After |
|--------|-------|
| `from taskforce.infrastructure.tools.registry import _TOOL_REGISTRY, register_tool` | `from taskforce.host import register_tool` |
| `from taskforce.application.profile_loader import register_config_dir` | `from taskforce.host import register_profile_dir` |
| `from taskforce_cli.agent_discovery import register_agent_config_dirs` | `from taskforce.host import register_profile_dir` (called per-dir) |
| `yaml.safe_load(open("my-profile.yaml"))` then inline params to `create_agent` | Drop the YAML loading; call `register_profile_dir(...)` and pass `config="my-profile"`. |
| Custom Telegram poller in your app | Use the Gateway's built-in poller via webhook OR run `taskforce serve` with `TELEGRAM_BOT_TOKEN`. |
| Custom OpenAI/Azure SDK calls in parallel to `AgentFactory` | Route everything through the same agent. Use the `python` tool for calculations, `wiki` for memory, `multimedia` for vision. |

The internal symbols still work — the migration is incremental.

---

## 10. Worked example: real-time chat app with Telegram + Web

A typical layout: a FastAPI host serves a web UI with WebSocket chat,
and Telegram users hit the same agent. **Sidecar mode** end-to-end:

```yaml
# docker-compose.yml
services:
  taskforce:
    image: ghcr.io/your-org/taskforce-with-mytools:latest   # taskforce + your tools
    command: ["taskforce", "serve", "--host", "0.0.0.0", "--port", "8070", "--workers", "2"]
    environment:
      AZURE_OPENAI_API_KEY: ${AZURE_OPENAI_API_KEY}
      AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
    volumes:
      - ./agents:/profiles
      - tf_data:/app/.taskforce
  webapp:
    image: my-org/webapp:latest
    depends_on: [taskforce]
    environment:
      TASKFORCE_URL: http://taskforce:8070
volumes:
  tf_data:
```

`webapp/main.py` (FastAPI):
```python
from fastapi import FastAPI, WebSocket
import httpx, json

app = FastAPI()
TF = "http://taskforce:8070"

@app.websocket("/ws/chat/{user_id}")
async def chat_ws(ws: WebSocket, user_id: str):
    await ws.accept()
    async with httpx.AsyncClient(base_url=TF, timeout=300) as tf:
        while True:
            text = (await ws.receive_json())["message"]
            async with tf.stream("POST", "/api/v1/execute/stream", json={
                "mission": text,
                "profile": "my-agent",
                "session_id": f"web-{user_id}",
            }) as r:
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        await ws.send_json(json.loads(line[6:]))
```

Telegram is configured **once** with the webhook (no code in `webapp`):
```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
     -d "url=https://your-public-domain/taskforce/api/v1/gateway/telegram/webhook?profile=my-agent"
```

A reverse proxy (Caddy/Traefik) routes `/taskforce/*` to the sidecar
and `/*` to `webapp`. Done — both channels share the same agent, the
same conversation store, and the same skills.

---

## 11. Troubleshooting

**`ImportError: cannot import name 'X' from 'taskforce.host'`**
You're on an older Taskforce version. `taskforce.host` was added in the
commit introducing [ADR-023](adr/adr-023-host-integration-api.md).
Upgrade.

**Tool not found at agent-build time** (`Unknown tool: my_tool`)
You called `create_agent()` before `register_tool()`. Move the
registration to your app's startup hook (FastAPI `lifespan`, Django
`ready()`, asyncio main entry).

**Profile not found** (`Profile 'my-profile' not found in any search dir`)
Either you forgot `register_profile_dir(...)` or the directory path is
relative to a different cwd than you expect. Pass an absolute path.

**Skills not appearing under `/api/v1/skills`**
The `SkillService` singleton was constructed before
`register_skill_dir(...)` was called. Either register before the first
call to any skill API, or rely on the late-registration refresh
(host API does this automatically — but only if the singleton already
exists).

**`taskforce serve` says "No such command 'serve'"**
The CLI binary is from `taskforce-cli`, not the framework. Install:
`uv pip install -e /path/to/pytaskforce/cli`. After installing or
reinstalling the CLI package, also re-source your shell so the
`taskforce` script is found.

**Telegram messages not arriving via webhook**
Run `curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"`
to see Telegram's last delivery error. Usually a missing public HTTPS
endpoint or signature mismatch.

**Streaming endpoint returns the whole reply at once instead of token-by-token**
Either you're hitting the synchronous `/execute` route (use
`/execute/stream`) or your reverse proxy is buffering. For nginx:
`proxy_buffering off;` for the SSE location.

---

## 12. Where to go next

* [ADR-023 — Host-App Integration API](adr/adr-023-host-integration-api.md) — design rationale.
* [REST API Guide](api.md) — full endpoint reference.
* [CLI Guide](cli.md) — every CLI command.
* [Profiles & Config](profiles.md) — profile schema, `extends:`, presets.
* [Plugin Development](plugins.md) — entry-point-based plugins.
* [Skills](features/skills.md) — context/prompt/agent skills.
* [External Integrations](integrations.md) — Telegram/Teams details.
* [Multi-Tenant Enterprise](features/enterprise.md) — RBAC, multi-tenancy.
