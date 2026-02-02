# Personal Assistant Plugin (Example)

This example packages a **personal assistant** toolset inside a single plugin.
It provides Google API-backed tools for **Gmail** and **Google Calendar**, plus
local demo tools for **tasks**, skills, and slash commands to structure workflows.

> ✅ Gmail and Calendar tools use Google APIs and require OAuth credentials.
> Tasks are stored locally in a JSON file for safe demo usage.

---

## 📁 Structure

```
personal_assistant/
├── personal_assistant/          # Plugin package
│   ├── tools/                   # Tool implementations
│   └── storage.py               # JSON-backed store helper
├── configs/                     # Profile configuration
├── skills/                      # Skill instructions
└── commands/                    # Slash command templates
```

---

## ✅ What You Get

### Tools (Plugin)
- `gmail` (actions: list, read, draft, send)
- `google_calendar` (actions: list, create)
- `task_list`, `task_create`, `task_complete`

Tasks read/write a local JSON file at:
```
.taskforce_personal_assistant/store.json
```

### Skills
- `daily-briefing`
- `inbox-triage`
- `calendar-assist`

### Slash Commands
- `/daily-briefing`
- `/inbox-triage`

---

## 🚀 Run the Plugin

```bash
# Install plugin dependencies
uv pip install -r examples/personal_assistant/requirements.txt

# Start a chat with the plugin
taskforce chat --plugin examples/personal_assistant --profile personal_assistant

# Run a mission
taskforce run mission "Prepare my daily briefing" \
  --plugin examples/personal_assistant \
  --profile personal_assistant
```

---

## 🔐 Gmail & Calendar Authentication

Provide OAuth credentials using one of these methods (in priority order):

### Option 1: Environment Variables (Recommended)

Set these once and forget:

```bash
# Either a token file path
export GOOGLE_TOKEN_FILE="/path/to/token.json"

# Or a short-lived access token
export GOOGLE_ACCESS_TOKEN="ya29.a0AfH6SM..."
```

Then run without extra arguments:
```bash
taskforce chat --plugin examples/personal_assistant --profile personal_assistant
```

### Option 2: Tool Parameters

Pass credentials per tool call:

- `access_token`: short-lived OAuth access token
- `token_file`: path to a `token.json` created by Google OAuth flow

```bash
taskforce run mission "List my inbox" \
  --plugin examples/personal_assistant \
  --profile personal_assistant \
  --tool-args '{"gmail": {"action": "list", "token_file": "/path/to/token.json"}}'
```

### Creating a token.json

1. Create OAuth credentials in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail API and Google Calendar API
3. Download `credentials.json` (Desktop app type)
4. Run the OAuth flow:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("token.json", "w") as f:
    f.write(creds.to_json())
```

---

## 🧠 Enable Skills

The profile in `configs/personal_assistant.yaml` points to the plugin skills
folder so the skills are discoverable automatically:

```
skills:
  directories:
    - "${PLUGIN_PATH}/skills"
```

---

## 🧭 Enable Slash Commands

Slash commands are discovered from `.taskforce/commands/` or `~/.taskforce/commands/`.
To use the example commands, copy or symlink them:

```bash
mkdir -p .taskforce/commands
cp examples/personal_assistant/commands/*.md .taskforce/commands/
```

---

## 🔌 Replace the Demo Store with Real Integrations

To connect real Gmail/Calendar APIs, replace the logic in:
- `personal_assistant/tools/email_tools.py`
- `personal_assistant/tools/calendar_tools.py`

Keep the tool interfaces stable so the profile and skills keep working.
