# REST API Guide

Taskforce includes a production-ready REST API built with **FastAPI**.

## Starting the Server

Run the server using `uvicorn`:
```bash
uvicorn taskforce.api.server:app --reload
```

## API Documentation

Once the server is running, you can access the interactive documentation at:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Key Endpoints

### Health Check

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Basic liveness check |
| `GET` | `/health/ready` | Readiness check with dependency health |

### Execution

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/execution/execute` | Run a mission synchronously |
| `POST` | `/api/v1/execution/execute/stream` | Run a mission with real-time SSE progress |
| `POST` | `/api/v1/execution/execute/{session_id}/cancel` | Cooperatively pause a running mission |

**Request body:**

```json
{
  "mission": "Build a REST API with auth",
  "profile": "butler",
  "conversation_id": "optional-id",
  "agent_id": "optional-agent-id",
  "planning_strategy": "native_react",
  "planning_strategy_params": {},
  "user_id": "optional",
  "org_id": "optional",
  "scope": "optional"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `mission` | string | **Required.** The task to execute |
| `profile` | string | Configuration profile (default: `butler`) |
| `conversation_id` | string | Resume or tag a conversation |
| `agent_id` | string | Use a specific agent (custom, profile, or plugin) |
| `planning_strategy` | string | Override strategy (native_react, plan_and_execute, plan_and_react, spar) |
| `planning_strategy_params` | object | Strategy-specific parameters |
| `user_id` | string | User ID for identity context |
| `org_id` | string | Organization ID for scoping |
| `scope` | string | RAG scope context |
| `session_id` | string | **Deprecated.** Use `conversation_id` instead |

**Response (sync):**

```json
{
  "session_id": "abc-123",
  "conversation_id": "conv-456",
  "status": "completed",
  "message": "Task completed successfully..."
}
```

**Error responses:**

| Status | Description |
|--------|-------------|
| 400 | Invalid request or configuration |
| 404 | Agent or profile not found |
| 409 | Execution cancelled |
| 500 | Unexpected server error |
| 502 | LLM or tool upstream error |

#### Streaming pause on `ask_user`

If the agent needs missing information, it emits an SSE event with `event_type: "ask_user"` and **stops streaming** (the agent is paused until you provide input). The event payload contains:

- **`details.question`**: the question to show the user
- **`details.missing`**: optional list of missing info items

To resume, call the same endpoint again with the same `conversation_id` and include the user's answer in `mission`.

### Communication Gateway (Telegram/MS Teams)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/gateway/{channel}/messages` | Handle normalized inbound messages |
| `POST` | `/api/v1/gateway/{channel}/webhook` | Handle raw provider webhooks |
| `POST` | `/api/v1/gateway/notify` | Send proactive push notification |
| `POST` | `/api/v1/gateway/broadcast` | Broadcast to all recipients on a channel |
| `GET` | `/api/v1/gateway/channels` | List configured communication channels |

Supported channels: `telegram`, `teams`

The gateway manages conversation history, session mapping, and outbound replies.

- Setup guide: see [External Integrations](integrations.md)
- Telegram requires `TELEGRAM_BOT_TOKEN` in `.env`

**Example: Send a Telegram message**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/gateway/telegram/messages",
    json={
        "conversation_id": "123456789",
        "message": "What did we discuss last time?",
        "sender_id": "user-42"
    }
)
print(response.json())
```

### Skills

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/skills` | List discovered skills |
| `GET` | `/api/v1/skills/{name}` | Read one skill's metadata and body |

Framework builds expose skills as read-only API resources. Enterprise builds own the write surface at `POST /api/v1/admin/skills`, where `skill:create` permission and tenant-scoped writable roots apply.

### Workflow Resume (Human-in-the-Loop)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/workflows/definitions` | List stored workflow definitions |
| `POST` | `/api/v1/workflows/definitions` | Create or replace a workflow definition |
| `GET` | `/api/v1/workflows/definitions/{workflow_id}` | Fetch a workflow definition |
| `DELETE` | `/api/v1/workflows/definitions/{workflow_id}` | Delete a workflow definition |
| `POST` | `/api/v1/workflows/definitions/{workflow_id}/run` | Execute a stored workflow definition in dependency order |
| `POST` | `/api/v1/workflows/webhooks/{trigger_path}` | Execute the workflow whose webhook trigger path matches |
| `POST` | `/api/v1/workflows/wait` | Persist a waiting checkpoint |
| `GET` | `/api/v1/workflows/{run_id}` | Fetch checkpoint state |
| `POST` | `/api/v1/workflows/{run_id}/resume` | Submit resume payload, transition to `resumed` |
| `POST` | `/api/v1/workflows/{run_id}/resume-and-continue` | Resume and continue via `activate_skill` |

Workflow definition payloads support `trigger_config` for trigger-specific settings and per-step `acp_peer` for ACP-mediated steps:
```json
{
  "workflow_id": "daily-report",
  "name": "Daily Report",
  "trigger": "chat",
  "trigger_config": {
    "match": "daily-report"
  },
  "steps": [
    {
      "step_id": "remote-summary",
      "agent": "reporter",
      "task": "Summarize today's activity",
      "acp_peer": "remote-reporter"
    }
  ]
}
```

**Example resume request:**
```json
{
  "input_type": "supplier_reply",
  "payload": {
    "supplier_reply": "VAT-ID DE123456789"
  },
  "sender_metadata": {
    "channel": "telegram",
    "sender_id": "123456"
  }
}
```

### Agents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/agents` | List all agents (custom, profile, plugin) |
| `GET` | `/api/v1/agents/{agent_id}` | Get a specific agent definition |
| `POST` | `/api/v1/agents` | Create a new custom agent |
| `PUT` | `/api/v1/agents/{agent_id}` | Update an existing custom agent |
| `DELETE` | `/api/v1/agents/{agent_id}` | Delete a custom agent |

#### Custom Agent Deployment

Custom agents (``source: "custom"``) must be **deployed** before they can be
invoked through ``POST /api/v1/execute``. The deploy endpoint runs preflight
validation (system prompt + tool allowlist + MCP wiring) and, on success,
records a ``deployed`` lifecycle entry under ``.taskforce/deployments/<agent_id>/``
which is then resolved by the execute gate. Profile and plugin agents are
not deployed — they are always available.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/agents/{agent_id}/deploy` | Validate and activate the current agent definition |
| `POST` | `/api/v1/agents/{agent_id}/rollback` | Re-activate a previously deployed version |
| `GET`  | `/api/v1/agents/{agent_id}/active` | Get the currently active deployment (`?environment=local\|staging\|prod`) |
| `GET`  | `/api/v1/agents/{agent_id}/deployments` | List the full deployment history (newest first) |

**Deploy request:**
```json
{
  "environment": "local",
  "deployed_by": "alice@example.com",
  "message": "Initial deploy"
}
```

All fields are optional — `environment` defaults to `local`.

**Deploy response (`200 OK`):**
```json
{
  "agent_id": "research_agent",
  "version": "2026-04-19T10:21:00+00:00",
  "status": "deployed",
  "environment": "local",
  "deployed_at": "2026-04-19T10:21:14+00:00",
  "deployed_by": "alice@example.com",
  "message": "Initial deploy",
  "rollback_from": null,
  "error": null,
  "config_snapshot": { "system_prompt": "...", "tool_allowlist": ["python"] }
}
```

**Preflight failures** return `400` (or `404` for `agent_not_found` /
`rollback_target_not_found`, `409` for `agent_not_custom`) with a structured
`ErrorResponse`. A `failed` record is also persisted to the deployment history
for debugging.

**Execute gating:** when `POST /api/v1/execute` is called with `agent_id`
referencing a custom agent that has no active deployment, the request is
rejected with `409 agent_not_deployed`.

#### Plugin Agent Discovery

The API automatically discovers plugin agents from the `examples/` and `plugins/` directories. Plugin agents are listed alongside custom and profile agents with `source: "plugin"`.

**Example: List all agents**
```python
import requests

response = requests.get("http://localhost:8000/api/v1/agents")
agents = response.json()["agents"]

# Filter plugin agents
plugin_agents = [a for a in agents if a["source"] == "plugin"]
for agent in plugin_agents:
    print(f"{agent['agent_id']}: {agent['name']}")
```

### Tool Catalog

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tools` | List all available tools with metadata |

Returns the full tool catalog including native, RAG, and plugin tools.

### Conversations (ADR-016)

Persistent conversation management — the replacement for sessions.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/conversations` | Create a new conversation |
| `GET` | `/api/v1/conversations` | List active conversations |
| `GET` | `/api/v1/conversations/archived` | List archived conversations |
| `GET` | `/api/v1/conversations/{id}/messages` | Get messages for a conversation |
| `POST` | `/api/v1/conversations/{id}/messages` | Send a message (runs agent, returns reply) |
| `POST` | `/api/v1/conversations/{id}/archive` | Archive a conversation |

### Cancelling a Running Mission

`POST /api/v1/execution/execute/{session_id}/cancel`

Cooperatively pauses a mission currently being executed for this
`session_id`. The agent completes its in-flight step (LLM call + tool
calls), persists its state, and exits with `status=paused`. A resume
happens transparently when the same `session_id` is used in the next
`/execute` or `/execute/stream` call.

**Response (202 Accepted):**

```json
{"session_id": "abc-123", "status": "interrupt_requested"}
```

**Response (404 Not Found)** when no active execution exists for the
given `session_id`:

```json
{"code": "session_not_running", "message": "...", "details": {"session_id": "abc-123"}}
```

**Example:**

```bash
# Terminal A — start a long-running mission
curl -N -X POST http://localhost:8000/api/v1/execution/execute/stream \
     -H 'Content-Type: application/json' \
     -d '{"mission": "analyse every file in the repo", "session_id": "run-1"}'

# Terminal B — pause it
curl -X POST http://localhost:8000/api/v1/execution/execute/run-1/cancel
# → 202 {"session_id": "run-1", "status": "interrupt_requested"}
```

The streaming response in Terminal A will emit an `interrupted` event
followed by a `complete` event with `status: "paused"` before the
connection closes.  See [ADR-019](adr/adr-019-agent-interruption.md).

### Memory Consolidation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/memory/consolidate` | Trigger memory consolidation pipeline |
| `GET` | `/api/v1/memory/experiences` | List captured session experiences |
| `GET` | `/api/v1/memory/consolidations` | List past consolidation runs |

**Consolidation request:**
```json
{
  "profile": "butler",
  "strategy": "default",
  "max_sessions": 10,
  "session_ids": ["optional-specific-session"]
}
```

### Admin APIs (Enterprise - Optional)

> **Note:** These endpoints are only available when `taskforce-enterprise` is installed.
> After installation, admin endpoints are automatically registered via the plugin system.

All admin endpoints require authentication via:
- **JWT Bearer Token**: `Authorization: Bearer <token>`
- **API Key**: `X-API-Key: <key>`

#### Tenant Management
- `GET /api/v1/admin/tenants` — List all tenants
- `POST /api/v1/admin/tenants` — Create a new tenant
- `GET /api/v1/admin/tenants/{tenant_id}` — Get tenant details
- `PUT /api/v1/admin/tenants/{tenant_id}` — Update tenant settings
- `DELETE /api/v1/admin/tenants/{tenant_id}` — Delete a tenant

#### User Management
- `GET /api/v1/admin/users` — List users for a tenant
- `POST /api/v1/admin/users` — Create a new user
- `GET /api/v1/admin/users/{user_id}` — Get user details
- `PUT /api/v1/admin/users/{user_id}` — Update user profile
- `DELETE /api/v1/admin/users/{user_id}` — Deactivate a user

#### Role Management
- `GET /api/v1/admin/roles` — List all roles
- `POST /api/v1/admin/roles` — Create a custom role
- `GET /api/v1/admin/roles/{role_id}` — Get role details
- `PUT /api/v1/admin/roles/{role_id}` — Update role permissions
- `DELETE /api/v1/admin/roles/{role_id}` — Delete a custom role

See [Enterprise Features](features/enterprise.md) for details on the RBAC system.

---

## Integration Examples

### Basic Mission Execution

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/execute",
    json={
        "mission": "Write a hello world in Rust",
        "agent_id": "coding_agent"
    }
)
print(response.json()["message"])
```

### Using Plugin Agents

```python
import requests

# List all available agents (including plugins)
agents_response = requests.get("http://localhost:8000/api/v1/agents")
all_agents = agents_response.json()["agents"]

# Execute with a plugin agent
response = requests.post(
    "http://localhost:8000/api/v1/execute",
    json={
        "mission": "Check invoice.pdf for completeness",
        "agent_id": "accounting_agent"
    }
)
```

### Custom Agent Management

```python
import requests

# Create a custom agent
create_response = requests.post(
    "http://localhost:8000/api/v1/agents",
    json={
        "agent_id": "web-scraper",
        "name": "Web Scraper Agent",
        "description": "Specialized agent for web scraping tasks",
        "system_prompt": "You are a web scraping expert...",
        "tool_allowlist": ["web_search", "web_fetch", "python"]
    }
)

# Use the custom agent
execute_response = requests.post(
    "http://localhost:8000/api/v1/execute",
    json={
        "mission": "Scrape product prices from example.com",
        "agent_id": "web-scraper"
    }
)
```


### Agent Deployment Contract (Management UI)

- After `POST /api/v1/agents`, the UI can immediately call `POST /api/v1/agents/{agent_id}/deploy`.
- Agent responses include: `deployment_status`, `deployment_active`, `active_version`, `deployed_at`, `ready_to_use`.
- `ready_to_use=true` maps to `deployment_status=deployed` and `deployment_active=true`.
- `POST /api/v1/execute` with `agent_id` checks deploy status for custom agents and accepts only active deployments.
