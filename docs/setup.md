# Setup & Installation

Taskforce ships in two editions and installs four ways. Pick the row that
matches you — the full walkthrough for each path is in
**[docs/install.md](install.md)**.

| You want… | Edition | Path |
| :--- | :--- | :--- |
| The quickest way on a desktop, no developer tools | Community | Native installer (`install.sh` / `install.ps1`) |
| To run it on a server / share it with a team | Community | Docker (`docker compose up`) |
| Multi-tenant, logins, RBAC, audit | Enterprise | See the `taskforce-enterprise` repository |
| To hack on Taskforce itself | either | From source with `uv` (below) |

## TL;DR — Community edition

**Native (Linux/macOS):**
```bash
curl -LsSf https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.sh | sh
taskforce up
```

**Native (Windows PowerShell):**
```powershell
irm https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.ps1 | iex
taskforce up
```

**Docker (desktop or server):**
```bash
git clone https://github.com/rudi77/pytaskforce && cd pytaskforce
cp .env.example .env        # then add your OPENAI_API_KEY
docker compose up -d        # open http://localhost:8070
```

Either way, `taskforce up` (or the container) starts the REST API **and**
the web UI from a single process and — for the native install — opens your
browser at <http://localhost:8070>.

## From source (developers)

Taskforce uses the **uv** package manager.

```bash
git clone https://github.com/rudi77/pytaskforce && cd pytaskforce
uv sync                         # framework + CLI + bundled agent packages
uv run playwright install chromium   # browser tool (optional)

# build the web UI so `taskforce up` can serve it
cd ui && pnpm install && pnpm run build && cd ..
cp -r ui/dist src/taskforce/api/_ui

cp .env.example .env            # add your OPENAI_API_KEY
uv run taskforce up
```

## Environment variables

Configuration lives in a `.env` file. The native installers write one to
`~/.taskforce/.env`; from source or Docker, copy `.env.example` to `.env`.

| Variable | Description |
| :--- | :--- |
| `OPENAI_API_KEY` | Required for OpenAI / LiteLLM models. |
| `DATABASE_URL` | Optional. SQLite by default; PostgreSQL for production. |
| `TASKFORCE_UI_DIR` | Optional. Override where the API looks for the built web UI. |
| `GITHUB_TOKEN` | Optional. Required for GitHub-related tools. |

Most runtime settings (LLM providers, channels, integrations) can also be
managed from **Settings** in the web UI once the server is running.

## Verifying the install

```bash
taskforce --help        # CLI is wired up
taskforce up            # API + web UI on http://localhost:8070
```

See **[docs/install.md](install.md)** for the detailed guide, upgrade and
uninstall steps, and the Enterprise edition.
