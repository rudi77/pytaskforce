# ACP Showcase — Three Taskforce Peers Working Together

This end-to-end demo runs **three real Taskforce agents** (LLM-backed) on
different ports, connected via the Agent Communication Protocol (ACP):

```
                     ┌────────────────────────┐
  user mission ──▶   │  orchestrator  :8800   │
                     │  plan_and_execute      │
                     └─┬────────────────────┬─┘
                       │ call_acp_agent     │ call_acp_agent
                       ▼                    ▼
           ┌─────────────────────┐  ┌─────────────────────┐
           │  researcher  :8801  │  │    coder    :8802   │
           │  web_search, fetch  │  │  python, file_write │
           └─────────────────────┘  └─────────────────────┘
```

**Mission run during the demo** (passed to the orchestrator):

> *Research the three most-used Python HTTP client libraries in 2026 and
> write a minimal working example using the recommended one. Save the
> example to `./examples/acp_showcase/out/demo_client.py`.*

The orchestrator plans the two stages, delegates research to the
`researcher` peer (`call_acp_agent` → `http://localhost:8801`), takes the
briefing back, then delegates the implementation to the `coder` peer
(`http://localhost:8802`), and finally composes a summary.

---

## Prerequisites

1. **ACP extra installed:**
   ```bash
   uv sync --extra acp
   ```
2. **LLM credentials in `.env`** (whichever provider your
   `src/taskforce/configs/llm_config.yaml` selects — e.g.,
   `AZURE_API_KEY` / `AZURE_API_BASE` / `AZURE_API_VERSION`, or
   `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`).
3. Free TCP ports **8800**, **8801**, **8802** on localhost.

---

## One-shot: `./run_demo.sh`

From the repo root:

```bash
./examples/acp_showcase/run_demo.sh
```

The script:

1. Starts `researcher` and `coder` peers in the background, redirecting
   their stdout/stderr to `examples/acp_showcase/logs/*.log`.
2. Waits until both ACP HTTP ports accept connections.
3. Sends the demo mission to the `orchestrator` via `taskforce run
   mission --profile showcase_orchestrator "…"`.
4. Prints the orchestrator's final answer and leaves the generated code
   in `examples/acp_showcase/out/demo_client.py`.
5. Shuts down both peer background processes.

Pass a custom mission as the first argument:

```bash
./examples/acp_showcase/run_demo.sh "Compare the top 3 async task queues and build a minimal Celery vs arq benchmark."
```

---

## Manual walk-through (three terminals — best for a live demo)

**Terminal A — researcher peer (port 8801):**

```bash
taskforce acp start --profile showcase_researcher
# → ACP server listening on 0.0.0.0:8801 (agent: 'researcher')
```

**Terminal B — coder peer (port 8802):**

```bash
taskforce acp start --profile showcase_coder
# → ACP server listening on 0.0.0.0:8802 (agent: 'coder')
```

**Terminal C — orchestrator: runs the mission that delegates to both peers**

```bash
taskforce run mission --profile showcase_orchestrator \
  "Research the three most-used Python HTTP client libraries in 2026 \
   and write a minimal working example using the recommended one. \
   Save the example to examples/acp_showcase/out/demo_client.py."
```

While it runs, you can watch the delegation live:

```bash
taskforce acp peers list --profile showcase_orchestrator
# Shows researcher + coder as configured peers.

taskforce acp call researcher "Who are you?" --profile showcase_orchestrator
# Fires a direct ACP run at the researcher peer — great for sanity checks.
```

---

## What to point out during the demo

- **Protocol openness** — replace `researcher` with any ACP-compliant
  agent (BeeAI, your own FastAPI, a partner's deployment). The
  orchestrator doesn't care, it just sees an ACP endpoint.
- **Clean architecture** — the orchestrator has zero knowledge of what
  tools the peers use internally; `call_acp_agent` treats them as a
  remote sub-agent.
- **Operational observability** — each peer writes its own
  `.taskforce/*` work dir and traces; they can live on different hosts.
- **Horizontal scalability** — adding a fourth role is *one new profile
  YAML + one line under `acp.peers`*. No orchestrator code change.

---

## Troubleshooting

- `Address already in use` → another process already owns 8800/8801/8802;
  change `acp.server.port` in the matching YAML.
- `Unknown peer: 'researcher'` → the orchestrator profile's `acp.peers`
  list is missing or the peer name doesn't match.
- `401 Unauthorized` from the LLM → your `.env` keys are missing or the
  wrong provider; double-check `src/taskforce/configs/llm_config.yaml`.
- `AttributeError: module 'uvicorn.config' has no attribute 'LoopSetupType'`
  → you have uvicorn ≥ 0.36 installed. The `acp` extra pins `uvicorn<0.36`
  because `acp-sdk` 1.0.x still references the pre-rename type. Re-run
  `uv sync --extra acp` to restore the pinned version and do not upgrade
  uvicorn manually until `acp-sdk` ships a fix.
- The agent loops on `web_fetch` errors → some search results may be
  unreachable; that's expected noise, the research step should still
  produce a briefing from the reachable sources.
