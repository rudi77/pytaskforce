# Installing Taskforce

Taskforce is built to be installed by **anyone** — not just developers —
on both desktop and server machines. This guide covers every supported
path.

## Editions

| Edition | What you get | Where it lives |
| :--- | :--- | :--- |
| **Community** | The full multi-agent framework: CLI, REST API, web UI, bundled agent packages (butler / coding / rag), tools, plugins. | this repository (`rudi77/pytaskforce`) |
| **Enterprise** | Everything in Community **plus** multi-tenant auth, RBAC, policy engine, admin API, audit trail, Postgres-backed identity. | `rudi77/taskforce-enterprise` |

The two editions are shipped as **separate artifacts** — separate Docker
images and separate installers. This page is the Community guide; for
Enterprise see the `taskforce-enterprise` repository's `docs/install.md`.

## Choosing a path

| | Native installer | Docker | From source |
| :--- | :--- | :--- | :--- |
| **Best for** | Desktop end users | Servers & teams, also desktops with Docker | Contributors |
| **Prerequisites** | none (binary mode) | Docker / Docker Desktop | git, uv, Node 20+ |
| **Updates** | re-run the installer | `docker compose pull` | `git pull && uv sync` |

All paths end the same way: a single process serves the REST API **and**
the web UI on port **8070**.

---

## 1. Native installer (Community)

The installer has two modes:

* **binary** (default) — downloads a prebuilt, self-contained bundle from
  GitHub Releases. **No Python, Node or git required.**
* **source** (`--from-source`) — clones the repository and installs with
  `uv`. Needs `git`; `uv`, Python and the web UI toolchain are handled
  automatically.

### Linux / macOS

```bash
# default (binary) mode
curl -LsSf https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.sh | sh

# or install from source
curl -LsSf https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.sh | sh -s -- --from-source
```

### Windows (PowerShell)

```powershell
# default (binary) mode
irm https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.ps1 | iex

# or install from source
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.ps1))) -FromSource
```

The installer:

1. installs Taskforce under `~/.taskforce` (override with `TASKFORCE_HOME`),
2. asks for your OpenAI API key and writes `~/.taskforce/.env`,
3. puts a `taskforce` launcher on your `PATH`
   (`~/.local/bin` on Unix, `%LOCALAPPDATA%\Taskforce\bin` on Windows).

Then:

```bash
taskforce up        # starts the app and opens http://localhost:8070
```

> **Browser tool:** the prebuilt bundle does not include the Chromium
> binary. If you need the browser tool, run `playwright install chromium`
> once (source mode does this for you).

---

## 2. Docker (Community)

Works identically on Linux servers, Windows and macOS (with Docker
Desktop).

```bash
git clone https://github.com/rudi77/pytaskforce
cd pytaskforce
cp .env.example .env          # edit .env: add OPENAI_API_KEY
docker compose up -d
```

Open <http://localhost:8070>. State (SQLite database, settings, logs)
persists in the `taskforce_data` Docker volume.

* Pull a newer image: `docker compose pull && docker compose up -d`
* Build locally instead of pulling: uncomment `build: .` in
  `docker-compose.yml`.
* Expose on a different port: change the `ports:` mapping.

The published image is `ghcr.io/rudi77/taskforce-community`.

---

## 3. From source (developers)

```bash
git clone https://github.com/rudi77/pytaskforce
cd pytaskforce
uv sync                              # framework + CLI + agent packages
uv run playwright install chromium   # browser tool (optional)

# Build the web UI so the API can serve it:
cd ui && pnpm install && pnpm run build && cd ..
cp -r ui/dist src/taskforce/api/_ui

cp .env.example .env                 # add OPENAI_API_KEY
uv run taskforce up
```

Without the web UI build the REST API still runs (`/docs`, `/api/v1/...`);
only the bundled front-end is unavailable. You can also point
`TASKFORCE_UI_DIR` at any directory containing a built UI.

---

## Building the release artifacts yourself

* **Docker image:** `docker build -t taskforce-community .`
* **PyInstaller bundle:** `uv run python scripts/build_exe.py --archive`
  — compiles the web UI, freezes the app and writes
  `dist/taskforce-community-<os>-<arch>.(tar.gz|zip)`.

Tagging a `v*` release runs `.github/workflows/release.yml`, which builds
and publishes all of the above automatically.

---

## Upgrading

| Path | Command |
| :--- | :--- |
| Native installer | re-run the install one-liner (keeps your `.env`) |
| Docker | `docker compose pull && docker compose up -d` |
| From source | `git pull && uv sync` |

## Uninstalling

| Path | Steps |
| :--- | :--- |
| Native installer | delete `~/.taskforce` and the `taskforce` launcher from your bin dir |
| Docker | `docker compose down -v` (the `-v` also removes the data volume) |
| From source | delete the cloned directory |

## Troubleshooting

* **`taskforce: command not found`** — the launcher directory is not on
  your `PATH`. The installer prints the line to add; on Windows, restart
  the terminal.
* **No web UI, only `/docs`** — the UI build was skipped. Build it (see
  *From source*) or use the Docker image / binary bundle, which include it.
* **Browser tool errors** — run `playwright install chromium`.
* **Port 8070 in use** — `taskforce up --port 9000`, or change the Docker
  `ports:` mapping.
