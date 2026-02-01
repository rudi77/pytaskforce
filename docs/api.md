# REST API Guide

Taskforce includes a production-ready REST API built with **FastAPI**.

## 🚀 Starting the Server

Run the server using `uvicorn`:
```powershell
uvicorn taskforce.api.server:app --reload
```

## 📖 API Documentation

Once the server is running, you can access the interactive documentation at:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## 🛣 Key Endpoints

### Execution
- `POST /api/v1/execution/execute`: Run a mission synchronously.
- `POST /api/v1/execution/execute/stream`: Run a mission with real-time SSE progress updates.

### Integrations (Telegram/MS Teams)
- `POST /api/v1/integrations/{provider}/messages`: Accept inbound messages and route them to the agent.
  - Supported providers: `telegram`, `teams`
  - The API maintains conversation history per provider conversation and maps it to a Taskforce `session_id`.
  - Setup guide: see [External Integrations](integrations.md).
  - Telegram push requires `TELEGRAM_BOT_TOKEN` in `.env`.

**Example: Send a Telegram message**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/integrations/telegram/messages",
    json={
        "conversation_id": "telegram:123456",
        "message": "Was haben wir zuletzt besprochen?",
        "profile": "dev"
    }
)
print(response.json())
```

#### Streaming pause on `ask_user`

If the agent needs missing information, it emits an SSE event with `event_type: "ask_user"` and **stops streaming** (the agent is paused until you provide input). The event payload contains:

- **`details.question`**: the question to show the user
- **`details.missing`**: optional list of missing info items

To resume, call the same endpoint again with the same `session_id` and include the user's answer in `mission` (or in `conversation_history`).

### Agents
- `GET /api/v1/agents`: List all available agents (custom, profile, and plugin agents).
- `GET /api/v1/agents/{agent_id}`: Get a specific agent definition.
- `POST /api/v1/agents`: Create a new custom agent.
- `PUT /api/v1/agents/{agent_id}`: Update an existing custom agent.
- `DELETE /api/v1/agents/{agent_id}`: Delete a custom agent.

#### Plugin Agent Discovery

The API automatically discovers plugin agents from the `examples/` and `plugins/` directories. Plugin agents are listed alongside custom and profile agents with `source: "plugin"`.

**Example: List all agents**
```python
import requests

response = requests.get("http://localhost:8000/api/v1/agents")
agents = response.json()["agents"]

# Filter plugin agents
plugin_agents = [a for a in agents if a["source"] == "plugin"]
for agent in plugin_agents:
    print(f"{agent['agent_id']}: {agent['name']}")
    print(f"  Path: {agent['plugin_path']}")
    print(f"  Tools: {agent['tool_classes']}")
```

**Example: Execute with plugin agent**
```python
import requests

# Use plugin agent by agent_id (plugin path is automatically resolved)
response = requests.post(
    "http://localhost:8000/api/v1/execution/execute",
    json={
        "mission": "Prüfe die Rechnung invoice.pdf",
        "agent_id": "accounting_agent"  # Plugin is automatically loaded
    }
)
```

### Sessions
- `GET /api/v1/sessions`: List all active sessions.
- `GET /api/v1/sessions/{session_id}`: Retrieve full state for a specific session.

### System
- `GET /health`: Basic liveness check.

### Admin APIs (Enterprise - Optional)

> **Hinweis**: Diese Endpoints sind nur verfügbar wenn `taskforce-enterprise` installiert ist.
>
> ```bash
> pip install taskforce-enterprise
> ```
>
> Nach Installation werden die Admin-Endpoints automatisch registriert via Plugin-System.

Die Admin APIs bieten Multi-Tenant-Management für Enterprise-Deployments.

#### Authentifizierung

Alle Admin-Endpoints erfordern Authentifizierung via:
- **JWT Bearer Token**: `Authorization: Bearer <token>`
- **API Key**: `X-API-Key: <key>`

```python
import requests

# Mit JWT Token
headers = {"Authorization": "Bearer eyJ..."}

# Mit API Key
headers = {"X-API-Key": "tk_..."}

response = requests.get(
    "http://localhost:8000/api/v1/admin/users",
    headers=headers
)
```

#### Tenant Management
- `GET /api/v1/admin/tenants`: List all tenants (requires `TENANT_MANAGE` permission).
- `POST /api/v1/admin/tenants`: Create a new tenant.
- `GET /api/v1/admin/tenants/{tenant_id}`: Get tenant details.
- `PUT /api/v1/admin/tenants/{tenant_id}`: Update tenant settings.
- `DELETE /api/v1/admin/tenants/{tenant_id}`: Delete a tenant.

#### User Management
- `GET /api/v1/admin/users`: List users for a tenant.
- `POST /api/v1/admin/users`: Create a new user.
- `GET /api/v1/admin/users/{user_id}`: Get user details.
- `PUT /api/v1/admin/users/{user_id}`: Update user profile.
- `DELETE /api/v1/admin/users/{user_id}`: Deactivate a user.

#### Role Management
- `GET /api/v1/admin/roles`: List all roles (system and custom).
- `POST /api/v1/admin/roles`: Create a custom role.
- `GET /api/v1/admin/roles/{role_id}`: Get role details with permissions.
- `PUT /api/v1/admin/roles/{role_id}`: Update role permissions.
- `DELETE /api/v1/admin/roles/{role_id}`: Delete a custom role.

#### System Roles (vordefiniert)

| Role | Permissions |
|------|-------------|
| `admin` | Alle Berechtigungen |
| `agent_designer` | Agent CRUD, Tool Read |
| `operator` | Agent Execute, Session CRUD |
| `auditor` | Read-only, Audit Read |
| `viewer` | Basis Read-only |

> **Siehe auch:** [Enterprise Features](features/enterprise.md) für Details zum RBAC-System und [Plugin System](architecture/plugin-system.md) für die Architektur.

## 🔧 Integration Examples

### Basic Mission Execution

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/execution/execute",
    json={
        "mission": "Write a hello world in Rust",
        "profile": "coding_agent"
    }
)
print(response.json()["message"])
```

### Using Plugin Agents

Plugin agents are automatically discovered and can be used by their `agent_id`:

```python
import requests

# List all available agents (including plugins)
agents_response = requests.get("http://localhost:8000/api/v1/agents")
all_agents = agents_response.json()["agents"]

# Find plugin agents
plugin_agents = [a for a in all_agents if a["source"] == "plugin"]
print("Available plugin agents:")
for agent in plugin_agents:
    print(f"  - {agent['agent_id']}: {agent['name']}")

# Execute with a plugin agent
response = requests.post(
    "http://localhost:8000/api/v1/execution/execute",
    json={
        "mission": "Prüfe die Rechnung invoice.pdf auf Vollständigkeit",
        "agent_id": "accounting_agent"  # Plugin is automatically loaded
    }
)
result = response.json()
print(f"Status: {result['status']}")
print(f"Message: {result['message']}")
```

### Custom Agent Management

```python
import requests

# Create a custom agent
create_response = requests.post(
    "http://localhost:8000/api/v1/agents",
    json={
        "agent_id": "web-scraper",
        "name": "Web Scraper Agent",
        "description": "Specialized agent for web scraping tasks",
        "system_prompt": "You are a web scraping expert...",
        "tool_allowlist": ["web_search", "web_fetch", "python"]
    }
)
print(f"Created agent: {create_response.json()['agent_id']}")

# Use the custom agent
execute_response = requests.post(
    "http://localhost:8000/api/v1/execution/execute",
    json={
        "mission": "Scrape product prices from example.com",
        "agent_id": "web-scraper"
    }
)
```
