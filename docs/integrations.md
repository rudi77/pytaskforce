# External Communication Integrations

This guide explains how to connect Taskforce to external chat providers such as
**Telegram**, **Microsoft Teams**, and other channels via the **Communication Gateway**.

The gateway provides a unified interface for:
- **Inbound messages** from any channel
- **Outbound replies** sent back through the originating channel
- **Proactive push notifications** initiated by agents or the API
- **Broadcast messages** to all registered recipients on a channel
- **Native webhook handling** with signature verification

> **Architecture Decision:** See [ADR-008](adr/adr-008-communication-gateway.md)
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
- Chat history is stored in `.taskforce/conversations/{channel}/`.
- Recipient references are stored in `.taskforce/recipients/{channel}/`.
- History is injected into the agent as `conversation_history` for each run.

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

1. **Implement `OutboundSenderProtocol`** in `taskforce_extensions/infrastructure/communication/`:

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
