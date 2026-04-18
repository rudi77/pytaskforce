# Agent Communication Protocol (ACP)

Taskforce supports the **Agent Communication Protocol (ACP)** so multiple
Taskforce instances — and any other ACP-compliant framework such as BeeAI —
can interoperate over an open, vendor-neutral REST/JSON protocol.

See **[ADR-018](../adr/adr-018-acp-protocol-support.md)** for the design
rationale.

## Install the optional dependency

```bash
uv sync --extra acp
```

All ACP imports are lazy — profiles without an `acp:` section work unchanged
even without the `acp-sdk` package installed.

## Three ways to use ACP

### 1. Host your agent as an ACP server

Add an `acp:` block to your profile YAML:

```yaml
acp:
  server:
    enabled: true
    host: 0.0.0.0
    port: 8800
    agent_name: taskforce_peer
    expose_profile: true
```

Start the server:

```bash
taskforce acp start --profile acp_peer
```

### 2. Call a remote ACP agent as a sub-agent

Register peers in your profile:

```yaml
acp:
  peers:
    - name: remote_coder
      base_url: https://coder.example.com/acp
      agent: coder
      auth:
        type: bearer
        token_env: ACP_TOKEN_CODER
```

Add the `call_acp_agent` tool to your tool list:

```yaml
tools:
  - file_read
  - call_acp_agent
```

Your orchestrator agent can now invoke the remote agent:

```json
{
  "tool": "call_acp_agent",
  "params": {
    "peer": "remote_coder",
    "mission": "Refactor module foo.py to use dataclasses"
  }
}
```

### 3. Use ACP as the distributed message bus

Swap the in-memory bus for the ACP-backed one:

```yaml
acp:
  message_bus:
    transport: acp
    publish_peers: [remote_coder]
    subscribe_topics: [tasks.new]
```

`publish(topic, payload)` triggers an ACP run named `bus_<topic>` on each
configured peer; `subscribe(topic)` registers a local handler that drains
incoming runs into an `asyncio.Queue`.

## CLI reference

```bash
taskforce acp start          # foreground ACP server for the current profile
taskforce acp status         # inspect the profile's ACP configuration
taskforce acp peers list     # show configured peers (profile + on-disk)
taskforce acp peers add mypeer --base-url http://host:8800 --agent coder \
                                --token-env ACP_TOKEN_MYPEER
taskforce acp peers remove mypeer
taskforce acp call mypeer "Refactor foo.py"
```

## API reference (read-only)

- `GET /api/v1/acp/peers` — list registered peers
- `GET /api/v1/acp/status` — summary of the on-disk registry

The actual ACP protocol endpoints (`/agents`, `/runs`, …) are served by the
embedded `acp_sdk.server.Server` on the port you configure under
`acp.server.port`.

## Security

- **Bearer auth** is the default; store tokens in environment variables and
  reference them via `auth.token_env`.
- **Shared secret** for the inbound gateway adapter is available via the
  constructor (`AcpInboundAdapter(shared_secret=…)`).
- **mTLS** is planned as a follow-up; the config schema already carries
  `cert_path` / `key_path` fields so profiles can be prepared ahead of time.

## Limitations

- Pub/sub semantics are emulated over ACP runs — acceptable for low/medium
  throughput but without broker-grade durability. A Kafka/NATS backend is
  tracked as a follow-up ADR.
- File attachments in the gateway outbound sender are not yet implemented.
- A future A2A merge (Linux Foundation) will require a new `AcpClient`
  backend; the `AcpClientProtocol` abstraction is already in place.
