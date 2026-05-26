# ADR-029: A2A (Agent-to-Agent) Protocol Support

**Status:** Accepted
**Date:** 2026-05-26

## Context

Taskforce adopted the **Agent Communication Protocol (ACP)** in
[ADR-018](adr-018-acp-protocol-support.md) as its inter-agent wire
protocol. Since then the Linux Foundation has consolidated the ecosystem
around the **A2A (Agent-to-Agent) protocol** — IBM officially merged ACP
into A2A in Sept 2025 and the upstream `acp-sdk` is on a deprecation
path. The A2A spec (v1.2, Mar 2026) is the de-facto open standard for
agent interoperability and ships an official Python SDK (`a2a-sdk`).

A2A is materially richer than ACP. It defines:

- a discoverable **Agent Card** at `/.well-known/agent-card.json`
  (RFC 8615),
- a task-centric lifecycle with **resumable streaming** (SSE),
- a first-class **`input-required`** state for HITL,
- named **artifacts** as task outputs,
- **push-notification webhooks** for asynchronous completion,
- multiple transports (JSON-RPC 2.0, REST, gRPC),
- a declarative auth surface (API key / Bearer / OAuth2 / OIDC / mTLS).

The user requirement: pytaskforce agents must be able to **discover
and connect** to remote agents over either protocol *and* be **findable
and invokable** by external agents over either protocol — without
breaking the existing ACP integration.

## Decision

Implement A2A as a **sibling stack** to ACP, with a thin **Hybrid
discovery facade** unifying peer enumeration only:

1. **Server** — each Taskforce instance can publish its profile agent
   as an A2A endpoint via `a2a-sdk` route builders (JSON-RPC + agent-
   card routes wired into a Starlette app run under uvicorn).
2. **Client** — remote A2A agents are callable as sub-agent tools
   through a new `call_a2a_agent` tool, sibling to `call_acp_agent`.
3. **Discovery facade** — `RemoteAgentDiscoveryService` enumerates
   ACP + A2A peers behind a single read-only `RemoteAgentDescriptor`
   view (CLI: `taskforce remote peers`, REST:
   `GET /api/v1/remote-agents`). The invocation paths stay
   protocol-specific.

`a2a-sdk` is an **optional dependency** (`uv sync --extra a2a`) —
imports are lazy via `infrastructure/a2a/_sdk.py` so profiles that
do not use A2A continue to work without the package installed.

Configuration lives in the profile YAML under a typed `a2a:` block
(`A2aConfigSchema`), with five sub-blocks (`server`, `peers`,
`artifacts`, `push`, plus `A2aAuthSchema` on both `server.auth` and
each peer's `auth`).

ACP **stays at parity** (no deprecation in pytaskforce) per user
decision — operators may run mixed ACP + A2A deployments indefinitely.

## Alternatives considered

- **Unified wire-level abstraction** over both protocols. Rejected:
  A2A's artifacts, push notifications, `input-required` state, OAuth2
  scopes-in-card and multi-transport selection have no ACP analogue.
  A single abstraction would either expose the lowest common
  denominator (losing A2A's value) or leak protocol-specific fields
  (defeating the purpose). The Hybrid facade unifies only the parts
  that *are* protocol-agnostic — peer enumeration, reachability,
  declared auth schemes.
- **Replace ACP with A2A.** Considered but rejected by user: ACP
  deployments continue to exist in the wild; pytaskforce should not
  break them. ACP is mostly feature-frozen but the integration is
  small and stable.
- **Use the community `python-a2a` package.** Rejected: it lags the
  official spec and is not Linux-Foundation-blessed. The official
  `a2a-sdk` is async-native, Apache 2.0, and the only SDK with
  spec-current types.

## Consequences

**Positive**
- Taskforce can federate with any A2A-compliant agent (Google ADK,
  CrewAI/A2A adapters, Pydantic AI, BeeAI's migrated server).
- `call_a2a_agent` slots into the existing orchestration tool
  registry alongside `call_acp_agent`.
- Existing ACP wiring (`infrastructure/acp/`, `application/acp_service`,
  CLI, routes) is untouched — A2A is purely additive.
- The Hybrid discovery facade gives operators one place to see all
  remote peers regardless of protocol.

**Negative / Follow-ups**
- Two protocol stacks to maintain. Mitigated by the sibling-stack
  layout: each protocol's failure mode is contained.
- Push-notifications require a publicly reachable callback URL.
  Polling fallback (`tasks/get` at `peer.poll_interval_seconds`) is
  shipped for local-dev / behind-NAT deployments.
- OAuth2 token resolution depends on `AuthManager` being wired
  (existing in pytaskforce). Static `token_env` continues to work for
  bearer/API-key auth.
- Spec movement: A2A still evolves. The SDK pin
  (`a2a-sdk>=1.0.3,<2.0.0`) plus lazy SDK loading isolates upstream
  changes from the rest of the codebase.

## Implementation

- **Core:** `core/interfaces/a2a.py`, `core/interfaces/remote_agent_discovery.py`,
  `core/domain/a2a.py`, `core/domain/remote_agent.py`.
- **Infrastructure:** `infrastructure/a2a/` —
  `_sdk.py` (lazy loaders), `peer_registry.py`
  (InMemory/File/Env/TenantScoped), `a2a_client.py`,
  `a2a_server.py`, `agent_card_builder.py`,
  `push_notification_handler.py`, `runtime.py`.
- **Application:** `application/a2a_service.py`,
  `application/remote_agent_discovery_service.py`,
  new `A2aConfigSchema` in `application/config_schema.py`,
  new `set_cross_tenant_a2a_authorizer` hook in
  `application/infrastructure_overrides.py`.
- **Tool:** `infrastructure/tools/orchestration/a2a_agent_tool.py`
  registered as `call_a2a_agent` in
  `infrastructure/tools/registry.py`.
- **CLI:** `api/cli/commands/a2a.py`
  (`start|status|call|peers|card`), `api/cli/commands/remote.py`
  (`peers|discover`).
- **REST:** `api/routes/a2a.py` (peer CRUD + test + webhook),
  `api/routes/remote_agents.py` (Hybrid view).
- **Example profile:** `src/taskforce/configs/a2a_peer.yaml`.
- **Optional dependency:** `[project.optional-dependencies].a2a =
  ["a2a-sdk>=1.0.3,<2.0.0"]` in `pyproject.toml`.

## Verification

End-to-end roundtrip confirmed during integration: A2A server
exposes a profile, client fetches the AgentCard, runs sync + stream
missions, the tool surfaces `state`, artifacts, and `needs_user_input`
flags. The Hybrid CLI (`taskforce remote peers`) lists ACP + A2A peers
side-by-side; REST (`GET /api/v1/remote-agents`) returns the same view.
All 108 pre-existing ACP / config-schema / acp-route tests still pass.
