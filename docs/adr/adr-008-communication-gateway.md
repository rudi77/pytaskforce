# ADR 008: Unified Communication Gateway

## Status
Accepted

## Context
Taskforce needed a unified interface for agent communication across multiple
channels (HTTP REST, Telegram, MS Teams, Slack, etc.). The previous architecture
(ADR-006) introduced `CommunicationProviderProtocol` for Telegram/Teams, but it
mixed three concerns in one protocol (session mapping, history persistence,
outbound delivery) and ran as a completely separate path from the REST execution
API. There was also no support for **proactive push notifications** -- agents
could only reply to inbound messages.

### Problems with the Previous Design
1. **Two disconnected execution paths** -- REST `/execute` and `/integrations/{provider}/messages` each created separate `AgentExecutor` instances with no shared session management.
2. **Mixed responsibilities** -- `CommunicationProviderProtocol` bundled session mapping, history persistence, and outbound delivery into a single protocol.
3. **Empty provider subclasses** -- `TelegramProvider` and `TeamsProvider` added no behavior over the base class.
4. **No push notifications** -- agents had no tool to proactively notify users.
5. **No inbound normalization** -- callers had to extract chat IDs from raw Telegram/Teams payloads before calling the API.
6. **Eager module-level initialization** -- services were instantiated at import time, outside the factory/DI system.

## Decision
We introduce a **Communication Gateway** with clean separation of concerns:

### 1. Four Focused Protocols (core/interfaces/gateway.py)

| Protocol | Purpose |
|----------|---------|
| `OutboundSenderProtocol` | Send messages to an external channel |
| `InboundAdapterProtocol` | Normalize raw webhooks + verify signatures |
| `ConversationStoreProtocol` | Channel-agnostic session mapping + history |
| `RecipientRegistryProtocol` | Manage push-notification recipients |

### 2. Domain Models (core/domain/gateway.py)

| Model | Purpose |
|-------|---------|
| `InboundMessage` | Normalized inbound message from any channel |
| `GatewayOptions` | Execution options (profile, agent_id, etc.) |
| `GatewayResponse` | Result of handling a message |
| `NotificationRequest` | Proactive push notification request |
| `NotificationResult` | Push notification delivery result |

### 3. CommunicationGateway (application/gateway.py)
Single orchestrator that handles:
- **Inbound path**: receive message -> resolve session -> load history -> execute agent -> persist history -> send outbound reply
- **Push path**: resolve recipient -> dispatch via outbound sender
- **Broadcast**: send to all registered recipients on a channel
- **Auto-registration**: automatically stores sender references for future push notifications

### 4. send_notification Tool (infrastructure/tools/native/)
A new native tool that allows agents to proactively send push notifications
during execution. Requires approval (MEDIUM risk). The tool delegates to the
`CommunicationGateway.send_notification()` method.

### 5. API Routes (api/routes/gateway.py)
| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/gateway/{channel}/messages` | Handle inbound messages (normalized) |
| `POST /api/v1/gateway/{channel}/webhook` | Handle raw provider webhooks |
| `POST /api/v1/gateway/notify` | Send proactive push notification |
| `POST /api/v1/gateway/broadcast` | Broadcast to all recipients |
| `GET  /api/v1/gateway/channels` | List configured channels |

### 6. Infrastructure Adapters
- `TelegramOutboundSender` -- shared `aiohttp.ClientSession`, Telegram Bot API
- `TeamsOutboundSender` -- stub for MS Teams Bot Framework
- `TelegramInboundAdapter` -- extracts chat_id/text from Telegram Updates
- `TeamsInboundAdapter` -- extracts conversation.id/text from Teams Activities
- `FileConversationStore` -- atomic file-based persistence
- `FileRecipientRegistry` -- file-based recipient reference storage

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │         CommunicationGateway             │
                    │         (application layer)              │
                    │                                          │
                    │  Inbound:  msg -> session -> agent -> reply
                    │  Push:     notify -> registry -> sender  │
                    │  Broadcast: all recipients -> sender     │
                    └────────┬──────────────┬──────────────────┘
                             │              │
              ┌──────────────┤              ├──────────────┐
              │              │              │              │
    ┌─────────▼──┐  ┌───────▼──┐  ┌───────▼──┐  ┌───────▼───────┐
    │ REST       │  │ Telegram │  │ Teams    │  │ send_         │
    │ /messages  │  │ /webhook │  │ /webhook │  │ notification  │
    │            │  │ inbound  │  │ inbound  │  │ tool          │
    │            │  │ +outbound│  │ +outbound│  │ (agent-init.) │
    └────────────┘  └──────────┘  └──────────┘  └───────────────┘
```

## Backward Compatibility
- The legacy `/api/v1/integrations/{provider}/messages` route is preserved.
- The old `CommunicationProviderProtocol`, `CommunicationService`, and provider
  classes remain importable for backward compatibility.
- New code should use the gateway APIs.

## Consequences
- **Unified entry point** -- all channels go through the same gateway.
- **Push notifications** -- agents can proactively notify users via any channel.
- **Clean separation** -- each protocol has a single responsibility.
- **Extensible** -- adding a new channel requires implementing `OutboundSenderProtocol`
  and optionally `InboundAdapterProtocol`.
- **Auto-registration** -- users are automatically registered for push notifications
  when they first interact via a channel.

## Alternatives Considered
- **Extend existing CommunicationProviderProtocol** -- rejected because it already
  mixed too many concerns and would become even more complex with push support.
- **Event bus for notifications** -- considered for future iteration. The current
  push mechanism is synchronous (tool-driven or API-driven). An event-based
  system (subscribe to agent events -> auto-notify) can be layered on top later.
