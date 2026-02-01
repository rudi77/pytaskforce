# ADR 006: Communication Provider Architecture (Telegram/Teams)

## Status
Accepted

## Context
Taskforce needs to communicate with users via external chat providers such as
Telegram and Microsoft Teams. The initial integration supports inbound messages,
but proactive outbound messages (agent-initiated notifications) require a clean
architecture that keeps provider-specific logic in infrastructure adapters.

## Decision
We introduce a **provider architecture** with:

1. **Core protocols** for external communication:
   - `CommunicationGatewayProtocol` for outbound messages.
   - `ConversationStoreProtocol` for session mapping and history persistence.
2. **Infrastructure adapters** in `taskforce_extensions/infrastructure/communication/`
   for concrete providers (Telegram, Teams) and storage backends.
3. **Application service** (`CommunicationService`) responsible for:
   - mapping provider conversation IDs to Taskforce `session_id`
   - loading/storing conversation history
   - invoking agent execution and dispatching outbound replies
4. **API entrypoints** under `/api/v1/integrations/{provider}/messages` to accept
   inbound provider events, with provider signature validation enforced upstream
   or via middleware.

## Consequences
- Provider-specific dependencies remain in the infrastructure layer.
- Conversation history and session mapping are consistent across providers.
- Outbound push messaging becomes possible by implementing gateway adapters
  without changing core logic.

## Alternatives Considered
- Embed provider SDKs directly in the API layer (rejected: violates clean
  architecture and complicates testing).
- Use a single generic webhook handler with no session mapping (rejected:
  breaks conversational continuity).
