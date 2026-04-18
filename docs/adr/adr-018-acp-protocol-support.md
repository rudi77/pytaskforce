# ADR-018: Agent Communication Protocol (ACP) Support

**Status:** Accepted
**Date:** 2026-04-18

## Context

Taskforce today offers three disconnected inter-agent communication paths:

1. `InMemoryMessageBus` for in-process coordination (single process only).
2. The Communication Gateway for *user-facing* channels (Telegram, Teams, REST).
3. `SubAgentSpawner` / `AgentTool` to invoke local sub-agents via `AgentFactory`.

None of these let multiple Taskforce deployments (or third-party frameworks
such as BeeAI) interoperate over an open, vendor-neutral wire protocol.
Users building distributed agent topologies had to wire ad-hoc HTTP or
message queues manually, duplicating what the ecosystem is standardising
around the **Agent Communication Protocol (ACP)** governed by the Linux
Foundation.

## Decision

Adopt ACP as the **inter-Taskforce** protocol and expose it in three roles:

1. **Server** — each Taskforce instance can expose its profile agent (and,
   optionally, message-bus topics) as ACP agents via `acp_sdk.server.Server`.
2. **Client** — remote ACP agents are callable as sub-agent tools through a
   dedicated `call_acp_agent` tool, re-using the existing orchestration
   pattern.
3. **Peer-to-peer bus** — a new `AcpMessageBus` implements
   `MessageBusProtocol` over ACP runs. `publish(topic, payload)` performs an
   ACP run on each configured peer (`bus_<topic>` agent name) and
   `subscribe(topic)` registers a local handler that drains into an
   `asyncio.Queue`.

All three roles share a single `AcpRuntime` façade that bundles the server,
a client pool and the peer registry. `acp-sdk` is an **optional** dependency
(`uv sync --extra acp`) — imports are lazy so profiles that do not use ACP
continue to work without the package installed.

Configuration lives in the profile YAML under a typed `acp:` block
(`AcpConfigSchema` in `application/config_schema.py`), with three sub-blocks
(`server`, `peers`, `message_bus`) validated by Pydantic.

## Alternatives considered

- **A2A (Agent-to-Agent, Google)** — overlapping spec that is in the process
  of merging with ACP under the Linux Foundation. Our abstraction over
  `AcpClientProtocol` / `AcpServerProtocol` lets a future A2A backend slot
  in without touching the core layer.
- **Custom HTTP/JSON endpoints** — fastest short-term, but reinvents
  discovery, session semantics and multi-part messages. ACP already defines
  these.
- **Extending the Communication Gateway with an "acp" channel only** —
  covers inbound/outbound but does not address peer-to-peer bus semantics.
  We therefore ship both: `AcpInboundAdapter` / `AcpOutboundSender` for the
  gateway *and* `AcpMessageBus` for distributed messaging.
- **Kafka / NATS broker** — strictly better for durability, but requires
  operators to run an additional broker. ACP-over-HTTP keeps the
  dependency footprint flat; durability is called out as a follow-up.

## Consequences

**Positive**

- Taskforce instances can now delegate missions and broadcast events to any
  ACP-compliant agent (BeeAI, other Taskforce deployments, custom servers).
- Existing orchestration code remains untouched — `AcpAgentTool` slots into
  the tool registry next to `call_agent` / `call_agents_parallel`.
- Message-bus transport is a one-line profile change (`transport: acp`).

**Negative / Follow-ups**

- ACP is request/response — pub/sub semantics are emulated on top of ACP
  runs. Acceptable for low/medium throughput; broker-grade durability is a
  follow-up ADR (Kafka / NATS backend for `MessageBusProtocol`).
- Authentication in this iteration is limited to bearer tokens (env-backed);
  mTLS is a follow-up.
- A future A2A merge under the Linux Foundation will require a `AcpClient`
  variant — the protocol abstractions above are designed with this in mind.

## Implementation

- Core: `core/interfaces/acp.py`, `core/domain/acp.py`.
- Infrastructure: `infrastructure/acp/` (`runtime.py`, `acp_server.py`,
  `acp_client.py`, `acp_message_bus.py`, `acp_gateway_adapters.py`,
  `peer_registry.py`).
- Application: `application/acp_service.py`,
  `application/config_schema.py` (new `AcpConfigSchema`).
- Tool: `infrastructure/tools/orchestration/acp_agent_tool.py` registered as
  `call_acp_agent` in `infrastructure/tools/registry.py`.
- API: read-only `/api/v1/acp/peers` and `/api/v1/acp/status` routes.
- CLI: `taskforce acp start|status|call|peers`.
- Example profile: `src/taskforce/configs/acp_peer.yaml`.
- Optional dependency group `acp` in `pyproject.toml`.
