# Setup & Installation

Taskforce uses the modern **uv** package manager for fast, reliable dependency management.

## 🪟 Windows Setup (PowerShell)

### 1. Install uv
If you don't have `uv` installed yet:
```powershell
pip install uv
```

### 2. Initialize Environment
```powershell
# Create the virtual environment
uv venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

# Sync dependencies
uv sync
```

## 🔐 Environment Variables

Taskforce requires several environment variables to function correctly. These are managed via a `.env` file.

1.  **Copy the template**:
    ```powershell
    Copy-Item .env.example .env
    ```
2.  **Edit `.env`**: At minimum, add your `OPENAI_API_KEY`.

### Key Variables
| Variable | Description |
| :--- | :--- |
| `OPENAI_API_KEY` | Required for OpenAI/LiteLLM models. |
| `DATABASE_URL` | PostgreSQL connection string (required for `prod` profile). |
| `GITHUB_TOKEN` | Optional. Required for GitHub-related tools. |

## 🧠 Optional: Long-Term Memory

Long-term memory is file-based and does not require any external services.
Enable the `memory` tool in your profile and point `memory.store_dir` to a
writable directory (typically under the profile `work_dir`). See
`docs/features/longterm-memory.md` for details.

## 🚀 Verifying the Install
Run the help command to ensure everything is wired correctly:
```powershell
taskforce --help
```
