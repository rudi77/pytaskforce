# External Communication Integrations

This guide explains how to connect Taskforce to external chat providers such as
**Telegram**, **Microsoft Teams**, and other channels via the **Communication Gateway**.

> **Looking to embed Taskforce in your application?** The [Integration Guide](integration-guide.md)
> covers the three integration modes (library / CLI / webservice), the public
> `taskforce.host` API, and end-to-end recipes for production deployments.
> This page focuses on the *channel side* — how the gateway talks to providers
> like Telegram and Teams once Taskforce is running.

> For **agent-to-agent** interoperability over the Agent Communication
> Protocol (ACP) — another Taskforce deployment, BeeAI, or any ACP-compliant
> framework — see the dedicated guide: [ACP integration](features/acp.md)
> ([ADR-018](adr/adr-018-acp-protocol-support.md)).

The gateway provides a unified interface for:
- **Inbound messages** from any channel
- **Outbound replies** sent back through the originating channel
- **Proactive push notifications** initiated by agents or the API
- **Broadcast messages** to all registered recipients on a channel
- **Native webhook handling** with signature verification

> **Architecture Decision:** See [ADR-009](adr/adr-009-communication-gateway.md)
> for the full design rationale.

---

## Gateway API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/gateway/{channel}/messages` | POST | Handle normalized inbound messages |
| `/api/v1/gateway/{channel}/webhook` | POST | Handle raw provider webhooks |
| `/api/v1/gateway/notify` | POST | Send proactive push notification |
| `/api/v1/gateway/broadcast` | POST | Broadcast to all recipients on a channel |
| `/api/v1/gateway/channels` | GET | List configured channels |

---

## Common Flow

### Option A: Normalized Messages

Send a pre-extracted message to the gateway:

```http
POST /api/v1/gateway/telegram/messages
Content-Type: application/json

{
  "conversation_id": "123456789",
  "message": "Wie ist der aktuelle Status?",
  "sender_id": "user-42",
  "profile": "dev"
}
```

### Option B: Raw Webhooks

Point your channel's webhook directly at Taskforce -- the gateway normalizes
the payload and verifies the signature automatically:

```http
POST /api/v1/gateway/telegram/webhook
Content-Type: application/json

{
  "update_id": 123456,
  "message": {
    "message_id": 789,
    "from": {"id": 42, "first_name": "Alice"},
    "chat": {"id": 123456789, "type": "private"},
    "text": "Wie ist der aktuelle Status?"
  }
}
```

The gateway will:
1. Verify the webhook signature (if configured)
2. Extract `chat_id`, `text`, and `sender_id` from the raw payload
3. Resolve or create a `session_id` for this conversation
4. Auto-register the sender for future push notifications
5. Execute the agent and return the reply
6. Send the reply back via the channel's outbound sender

### Response Format

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "reply": "Der aktuelle Status ist...",
  "history_length": 4
}
```

---

## Telegram Setup

### 1) Create a Bot

Use **@BotFather** to create a bot and get a token.

### 2) Configure Environment

```bash
export TELEGRAM_BOT_TOKEN=your-telegram-bot-token
```

This enables both inbound webhook handling and outbound message delivery.

### 3) Register the Webhook

Point Telegram directly at the gateway webhook endpoint:

```bash
curl -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://your-domain.example/api/v1/gateway/telegram/webhook"
```

That's it -- the gateway handles message extraction, session management,
agent execution, and reply delivery automatically.

### Alternative: External Webhook Handler

If you prefer to handle webhooks yourself (e.g., for additional processing):

```python
import requests

def handle_telegram_update(update: dict) -> None:
    chat_id = update["message"]["chat"]["id"]
    text = update["message"]["text"]
    sender_id = update["message"]["from"]["id"]

    requests.post(
        "http://localhost:8000/api/v1/gateway/telegram/messages",
        json={
            "conversation_id": str(chat_id),
            "message": text,
            "sender_id": str(sender_id),
            "profile": "dev",
        },
        timeout=30,
    )
```

---

## Microsoft Teams Setup

### 1) Create a Teams Bot

Create a bot in **Azure Bot Service** and enable the **Microsoft Teams** channel.

### 2) Configure Environment

```bash
export TEAMS_APP_ID=your-bot-app-id
export TEAMS_APP_PASSWORD=your-bot-password
```

### 3) Configure the Messaging Endpoint

Point your bot's messaging endpoint to:

```
https://your-domain.example/api/v1/gateway/teams/webhook
```

The gateway extracts `conversation.id`, `text`, and `from.id` from the
Teams Activity payload automatically.

---

## Proactive Push Notifications

Agents can proactively send notifications to users who have previously
interacted via a channel. Recipients are **auto-registered** when they first
send a message through the gateway.

### Via API

```http
POST /api/v1/gateway/notify
Content-Type: application/json

{
  "channel": "telegram",
  "recipient_id": "42",
  "message": "Dein Report ist fertig!"
}
```

### Via Agent Tool

Agents can use the `send_notification` tool during execution:

```yaml
# In profile YAML - add to tools list
tools:
  - send_notification
  - file_read
  - python
  # ...
```

The agent can then call:

```json
{
  "tool": "send_notification",
  "params": {
    "channel": "telegram",
    "recipient_id": "42",
    "message": "Analyse abgeschlossen. 3 Probleme gefunden."
  }
}
```

### Broadcast

Send a message to all registered recipients on a channel:

```http
POST /api/v1/gateway/broadcast
Content-Type: application/json

{
  "channel": "telegram",
  "message": "System-Update: Neue Features verfuegbar!"
}
```

---

## Session & History Behavior

- Each channel conversation maps to a Taskforce `session_id`.
- Subsequent messages resume the same session automatically.
- Gateway session/history records are stored in `.taskforce/gateway_sessions/{channel}/` (`GatewayConversationStore`). Domain conversations from ADR-016 live separately under `.taskforce/conversations/`.
- Recipient references are stored in `.taskforce/recipients/{channel}/`.
- History is injected into the agent as `conversation_history` for each run.

---

## Telegram Action Transparency (`/actions`)

Per [issue #157](https://github.com/rudi77/pytaskforce/issues/157), the Communication Gateway records the tool-call activity of every user turn so that channel users can see *what* the agent did, not just the final answer.

Two complementary surfaces are provided:

### `/actions` slash command

Send `/actions` in any chat (Telegram, REST, etc.) to receive a compact, ASCII-formatted summary of the **previous** user turn:

```
Actions for previous turn (3 tools, 2 ok, 1 fail):
1. [ok] file_read {"path": "expenses.csv"} (12 ms)
2. [ok] python {"code": "df = pd.read_csv..."} (240 ms)
3. [fail] send_notification {"recipient_id": "u-1"} (5 ms) — 401 Unauthorized
```

If no prior turn has been recorded for this conversation the gateway replies with:

```
No prior actions in this conversation.
```

The slash command is **always available**, regardless of `actions_summary_mode`. It does not invoke the agent and never resets conversation history (so it is safe to chain after `/start`).

### Optional `actions_summary: footer` mode

Set the env var `TASKFORCE_ACTIONS_SUMMARY=footer` (default `disabled`) to have a one-line summary appended to **every** outbound channel reply:

```
… <agent's normal reply> …

— Actions: 3 tools (2 ok, 1 fail)
```

The footer is opt-in to avoid spamming users who don't want it. When no tools fired during a turn, no footer is appended. The `/actions` command works in either mode; the env var only controls the always-on footer.

### Storage and retention

- Logs live in process memory and are capped per conversation (default 10 turns; set via the `max_action_logs` constructor argument).
- Each record includes the tool name, a truncated args summary, success/failure, optional error message, and duration in milliseconds.
- Markers are intentionally ASCII (`[ok]` / `[fail]`) rather than emoji to comply with the project's emoji-only-on-request rule.

### Limitations

- Recording is wired into the legacy gateway path and the ADR-016 ConversationManager path. The optional `request_queue` (ADR-016 Phase 4) routes execution outside the gateway and currently records nothing — fixable in a future iteration once the queue surfaces tool events.
- Logs are not persisted across restarts; they live in process memory only.

---

## Channel Comparison

| Channel | Proactive Push | Webhook Support | Signature Verification |
|---------|---------------|-----------------|----------------------|
| Telegram | Yes (anytime) | Yes (native) | Secret token header |
| Teams | Yes (with ConversationReference) | Yes (native) | JWT validation (planned) |
| REST | N/A | N/A | N/A |

---

---

## Adding a New Channel

To add support for a new channel (e.g., Slack, Discord):

1. **Implement `OutboundSenderProtocol`** in `taskforce/infrastructure/communication/`:

```python
class SlackOutboundSender:
    @property
    def channel(self) -> str:
        return "slack"

    async def send(self, *, recipient_id, message, metadata=None) -> None:
        # POST to Slack chat.postMessage API
        ...
```

2. **Implement `InboundAdapterProtocol`** (optional, for webhook support):

```python
class SlackInboundAdapter:
    @property
    def channel(self) -> str:
        return "slack"

    def extract_message(self, raw_payload) -> dict:
        # Extract channel_id, text, user_id from Slack event
        ...

    def verify_signature(self, *, raw_body, headers) -> bool:
        # Verify Slack signing secret
        ...
```

3. **Register in `gateway_registry.py`** -- add to `build_gateway_components()`.

4. **Add environment variable** -- e.g., `SLACK_BOT_TOKEN`.

No changes to the gateway, domain models, or API routes are needed.

---

## Google Workspace Integration

Taskforce includes built-in tools for **Google Calendar**, **Gmail**, and **Google Drive**.
All three use the same OAuth2 token stored at `~/.taskforce/google_token.json`.

### Setup

1. **Install dependencies:**

```bash
uv sync
```

2. **Create OAuth credentials** in Google Cloud Console (OAuth 2.0 Client ID, type "Desktop app").
   Download the JSON and save it as `~/.taskforce/google_credentials.json`.

3. **Run the authorization flow:**

```bash
python scripts/google_auth.py
```

This opens a browser for consent and saves the token. The following scopes are requested:
- `calendar` — Google Calendar read/write
- `gmail.readonly` — Gmail read access
- `tasks.readonly` — Google Tasks read access
- `drive` — Google Drive full access

> **Note:** If you authorized before the Drive scope was added, re-run
> `python scripts/google_auth.py` to update your token.

### Available Tools

| Tool | Short Name | Description |
|------|-----------|-------------|
| Google Calendar | `calendar` | List, create, update, delete calendar events |
| Gmail | `gmail` | List, read emails and labels (read-only) |
| Google Drive | `google_drive` | List, get, download, upload, update, delete files; create folders; search |

### Google Drive Actions

| Action | Description |
|--------|-------------|
| `list` | List files in a folder (default: root) |
| `get` | Get file metadata |
| `download` | Download content (exports Google Docs/Sheets/Slides to text) |
| `upload` | Create a new text file |
| `update` | Update file content or name |
| `delete` | Delete a file |
| `create_folder` | Create a new folder |
| `search` | Search using Drive query syntax (e.g., `name contains 'report'`) |

### Profile Configuration

Add the tools to your agent profile:

```yaml
tools:
  - gmail
  - google_drive
  - calendar
```

The `butler.yaml` profile includes all three tools by default.

### Butler daemon hardening (24/7 operation)

`taskforce butler start` wraps the daemon in a
``DaemonSupervisor`` (see
`agents/butler/src/taskforce_butler/daemon_supervisor.py`) that adds
the runtime guarantees needed for unattended operation (issue #156):

- **Watchdog**: every supervisor tick checks
  ``ButlerDaemon.last_heartbeat`` (refreshed by the status-writer
  loop). If the heartbeat falls behind ``stall_threshold_seconds``
  (default 120s), the supervisor logs
  ``event="butler.daemon.stall_detected"`` and restarts the daemon.
- **Auto-restart on crash**: uncaught exceptions are logged via
  ``logger.exception("butler.daemon.crash", ...)`` with
  ``iteration_count``, ``restart_count``, ``backoff_seconds`` and the
  error type. The supervisor sleeps for an exponential backoff (1s,
  2s, 4s … capped at 60s) before restarting. ``KeyboardInterrupt``,
  ``SystemExit`` and ``asyncio.CancelledError`` propagate, so manual
  shutdown is never converted into a restart.
- **Graceful shutdown on signals**: ``SIGINT`` is handled on every
  platform; ``SIGTERM`` is handled on POSIX, ``SIGBREAK`` on Windows.
  The handler flips an asyncio event so the supervisor stops the
  inner daemon (which drains in-flight scheduler jobs and persistent
  agent requests via the existing ``ButlerService.stop`` /
  ``PersistentAgentService.stop`` paths) and exits cleanly.
- **Transient LLM-failure retries**: ``LiteLLMService`` already
  retries 429/502/503/timeouts via
  ``retry.max_attempts``/``retry.backoff_multiplier`` in
  ``llm_config.yaml``. Auth/quota errors (401/403, ``insufficient_quota``,
  ``billing``) are now classified as non-retryable so a rotated API
  key doesn't burn through retry budget every tick.

Disable supervision with ``taskforce butler start --no-supervisor``
when running under an external init system (systemd, Docker, k8s) that
already provides its own restart policy.

### Approval-gate failure surfacing (issue #190 sub-item a)

When a tool that declares ``requires_approval=True`` is blocked by the
human-approval gate, the resulting tool_result carries a structured
``error_kind`` so downstream consumers (UI, react loop, learning
service) can react appropriately instead of treating the block as a
generic tool failure.

| Gate outcome | ``approval_status`` | ``error_kind`` | ``terminal_failure`` |
|---|---|---|---|
| User said no | ``denied`` | ``approval_denied`` | ``true`` |
| No admin response in time | ``timed_out`` | ``approval_timeout`` | ``true`` |
| Approval pipeline crashed | ``error`` | ``approval_error`` | ``true`` |
| Pre-gate ``validate_params`` rejected | ``error`` | ``approval_error`` | ``false`` (retry with corrected args is fine) |

The react loop reads ``error_kind`` from the ``tool_result`` event and,
when at least one failed tool was approval-blocked, injects a
different retry nudge:

```
[System: Approval was denied for <tool>. Do NOT retry this action,
NOR any tool that would have the same effect. In your next reply,
tell the user in plain language that the action was not permitted
and ask what they would prefer instead.]
```

This closes the action-gap path where the LLM saw a generic
"calendar_create failed" message, fell back to ``shell``/``python``,
and silently re-attempted the same forbidden side-effect.
