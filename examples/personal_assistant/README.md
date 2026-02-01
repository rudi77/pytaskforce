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

Provide OAuth credentials using one of these inputs:

- `access_token`: pass a short-lived OAuth access token
- `token_file`: path to a `token.json` created by Google OAuth flow

Example (token file):
```bash
taskforce run mission "List my inbox" \
  --plugin examples/personal_assistant \
  --profile personal_assistant \
  --tool-args '{"gmail": {"action": "list", "token_file": "/path/to/token.json"}}'
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
