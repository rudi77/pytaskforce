# External Communication Integrations

This guide explains how to connect Taskforce to external chat providers
such as **Telegram** and **Microsoft Teams**. The integration flow uses the
`/api/v1/integrations/{provider}/messages` endpoint, which maps each provider
conversation to a Taskforce `session_id` and persists chat history.

> **Security note:** The integration endpoint does not perform provider-specific
> signature verification. Place it behind your API gateway and validate provider
> signatures/tokens there, or add validation middleware in your deployment.

---

## ✅ Common Flow

1. **Receive incoming webhook** from the provider.
2. **Extract provider conversation identifiers** (Telegram `chat_id`, Teams
   `conversation.id`, etc.).
3. **Send the inbound payload** to Taskforce:

```http
POST /api/v1/integrations/{provider}/messages
Content-Type: application/json

{
  "conversation_id": "provider-specific-id",
  "message": "User message",
  "profile": "dev"
}
```

Taskforce will:
- resolve or create a `session_id` for this conversation
- store chat history in `.taskforce/conversations/`
- pass `conversation_history` into the agent

---

## 🟦 Telegram Setup

### 1) Create a bot
Use **@BotFather** to create a bot and get a token.

### 2) Expose a webhook receiver
Create a small webhook service (FastAPI/Flask) that Telegram can call. Example
flow inside your webhook handler:

```python
import requests

def handle_telegram_update(update: dict) -> None:
    chat_id = update["message"]["chat"]["id"]
    text = update["message"]["text"]

    requests.post(
        "http://localhost:8000/api/v1/integrations/telegram/messages",
        json={
            "conversation_id": str(chat_id),
            "message": text,
            "profile": "dev",
        },
        timeout=10,
    )
```

### 3) Register the webhook
```bash
curl -X POST \
  "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://your-domain.example/telegram/webhook"
```

---

## 🟪 Microsoft Teams Setup

### 1) Create a Teams Bot
Create a bot in **Azure Bot Service** and enable the **Microsoft Teams**
channel. Copy the **Bot App ID** and **Password**.

### 2) Handle incoming messages
Teams sends messages with a `conversation.id`. Use it as the
`conversation_id` for Taskforce.

```python
import requests

def handle_teams_activity(activity: dict) -> None:
    conversation_id = activity["conversation"]["id"]
    text = activity.get("text", "")

    requests.post(
        "http://localhost:8000/api/v1/integrations/teams/messages",
        json={
            "conversation_id": conversation_id,
            "message": text,
            "profile": "dev",
        },
        timeout=10,
    )
```

### 3) Configure the messaging endpoint
Set your bot’s messaging endpoint to your webhook handler, e.g.:

```
https://your-domain.example/teams/webhook
```

---

## ✅ Session & History Behavior

- Each provider conversation maps to a Taskforce `session_id`.
- Subsequent messages resume the same session automatically.
- Chat history is stored in `.taskforce/conversations/` and injected into each run.

If you want per-user sessions (instead of per-conversation), combine
`conversation_id` with the user ID in your webhook handler.
