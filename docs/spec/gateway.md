---
feature: gateway
status: shipped
since: 2026-02-06
last_verified: 2026-05-16
owner: rudi77
adr: ADR-009
---

# Communication Gateway — Unified Channel Layer

A single entry point that lets the agent talk to users on any external
communication channel (Telegram, MS Teams, Slack, generic webhooks, REST).
The same gateway handles inbound messages, raw provider webhooks (with
signature verification and attachment download), proactive push, broadcasts,
and the `/link <code>` pairing flow that ties a channel sender to a logical
user. Channel-specific behaviour is hidden behind protocol implementations
so the agent code stays channel-agnostic.

## Capabilities (what the user can do)

- send a message from any configured channel and get an agent reply
- have a third-party provider (Telegram bot, Teams webhook) deliver raw webhook payloads that the gateway normalises and dispatches
- receive proactive push notifications from the agent on a single channel
- be one of many recipients of a broadcast on a channel
- mint a one-time pairing code in the web UI and pair their channel account by typing `/link <code>` on that channel
- remove their own channel pairings on demand
- list which channels are currently configured

## Invariants (what must always be true)

- Raw webhook payloads must pass channel-specific signature verification before any agent code runs. A failed signature returns 401 and the payload is discarded.
- A `/link` pairing code is single-use; a second consumption returns null and the link is unchanged.
- Pairing codes expire after their TTL (60–3600 seconds, default 600). An expired or unknown code returns null on consume.
- Two unexpired pairing codes for the same channel cannot collide.
- The `/link` command in chat is intercepted by the gateway BEFORE the recipient resolver runs, so an unpaired user can complete pairing without being known to the identity layer.
- Inbound Telegram attachments (photos, documents) are auto-downloaded server-side and added to the message before agent execution.
- Sender and adapter configurations (bot tokens, credentials) are re-read per outbound call so live updates via the settings store apply immediately.
- A new `/link` from a sender that was already paired overwrites the existing link (operator intent: the newest pairing always wins).
- Conversation history and session mapping survive process restart (file-backed by default).

## API surface (the contract clients depend on)

- POST /api/v1/gateway/{channel}/messages → 200 with agent reply
- POST /api/v1/gateway/{channel}/messages → 400 on empty message
- POST /api/v1/gateway/{channel}/webhook → 200 with agent reply
- POST /api/v1/gateway/{channel}/webhook → 400 on unknown channel or malformed payload
- POST /api/v1/gateway/{channel}/webhook → 401 on signature verification failure
- POST /api/v1/gateway/notify → 200 with per-recipient success/error
- POST /api/v1/gateway/notify → 400 on empty message
- POST /api/v1/gateway/broadcast → 200 with per-recipient breakdown (total/sent/failed)
- POST /api/v1/gateway/broadcast → 400 on empty message
- GET  /api/v1/gateway/channels → 200 with sorted list of channel names
- POST /api/v1/gateway/{channel}/link-codes → 200 with code, channel, expires_at, ttl_seconds
- POST /api/v1/gateway/{channel}/link-codes → 400 on TTL out of range (60–3600)
- DELETE /api/v1/gateway/{channel}/links/me → 200 with count of removed links

## Extension points

All eight protocols below can be replaced by enterprise plugins or host
applications via override functions in `taskforce.application.infrastructure_overrides`.
The framework ships file-based / in-memory defaults for everything except
`AgentLookupProtocol` and `WorkflowLookupProtocol` (no default — without
them, `@name` mentions fall through to plain text).

- `OutboundSenderProtocol` — channel-specific message and file dispatch
- `InboundAdapterProtocol` — channel-specific payload normalisation and signature verification
- `ConversationStoreProtocol` — channel-agnostic session mapping and history persistence
- `RecipientRegistryProtocol` — persistent store for push-notification recipient references
- `RecipientResolverProtocol` — channel identity → logical recipient mapping (pass-through default; enterprise: identity-aware)
- `ChannelLinkRegistryProtocol` — pairing flow registry (file default; enterprise: postgres tenant-scoped)
- `AgentLookupProtocol` — `@agent_name` mention resolution (tenant-scoped by construction; no framework default)
- `WorkflowLookupProtocol` — `@workflow_name` mention resolution (tenant-scoped by construction; no framework default)

## Tests (must exist and pass)

- spec("gateway.webhook_invalid_signature_returns_401")
- spec("gateway.webhook_telegram_attachments_downloaded")
- spec("gateway.webhook_unknown_channel_returns_400")
- spec("gateway.notify_empty_message_returns_400")
- spec("gateway.broadcast_partial_failure_reports_per_recipient")
- spec("gateway.link_code_single_use")
- spec("gateway.link_code_expires_after_ttl")
- spec("gateway.link_code_invalid_ttl_returns_400")
- spec("gateway.link_command_intercepted_before_resolver")
- spec("gateway.relink_overwrites_existing")
- spec("gateway.outbound_sender_reread_per_call")
- spec("gateway.channels_list_sorted")

## Known gaps

- **No authentication on `POST /notify` and `POST /broadcast`** — anyone with network access can send notifications to any registered recipient. Tracked in #278; once fixed, add `requires permission "notify:send"` claims to the API surface.
- **`POST /messages` accepts client-supplied `user_id`, `org_id`, `scope`** in the body and passes them straight to the executor as user context. An attacker can spoof identity for RAG queries. Tracked in #280.
- **Webhook signature verification has no replay protection.** A captured legitimate payload can be replayed indefinitely. Tracked in #285.
- **Telegram `InboundAdapter.verify_signature()` fail-opens** when no bot token is configured or when the secret-token header is missing. A misconfigured production instance silently accepts any payload. Tracked in #286.
- **SSE stream error events leak stack traces** including exception type and message — recon material. Tracked in #288.
- **`_download_telegram_attachments` reads `TELEGRAM_BOT_TOKEN` from `os.getenv` directly**, bypassing the settings store. Live token rotation via settings does not affect attachment downloads.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test".
- **No tests assert auth on `/notify` and `/broadcast`** — even after #278 lands, regression coverage is needed. Tracked in #372.
- **`_build_user_context()` returns the raw client values without any authority check.** Same root cause as #280 but separate code path worth listing.

## Cross-references

- adr: ADR-009 (Communication Gateway — primary design)
- adr: ADR-006 (per-provider providers — predecessor, deprecated)
- related_spec: channel-ask.md (uses the gateway's question/answer flow)
- related_spec: multi-tenant.md (override hooks are the tenant-scoping seam)
- docs: docs/integrations.md (user-facing setup guide for each channel)
- commit: 130279a (introduced 2026-02-06)
- commit: 72007b0 (per-user `/link` pairing, 2026-05-12, issue #162)
- commit: 38eb5da (per-call gateway component re-read, 2026-05-04, ADR-022 G1)
- commit: eb77a8c (@workflow_name mention resolution, 2026-05-04, ADR-022 G5)
