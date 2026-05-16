---
feature: cli
status: shipped
since: 2026-01-02
last_verified: 2026-05-16
owner: rudi77
adr: ADR-026
---

# Unified CLI — `taskforce` Command Surface

The `taskforce` executable is the single entry point operators and developers
use to drive every framework feature locally — running missions, interactive
chat, managing tools and skills, booting the REST API + web UI, and starting
the agent daemon. The unified CLI (`taskforce_cli`) auto-discovers agent
packages (Butler, coding-agent, RAG) and their subcommands via the
`taskforce.cli_apps` / `taskforce.tools` / `taskforce.config_dirs` entry-point
groups, so installing an agent package makes new commands and profiles appear
without any framework code change. If `taskforce_cli` is not installed, the
framework ships a fallback CLI with the core commands only.

## Capabilities (what the user can do)

- run `taskforce --help` after `uv pip install taskforce` (or `pip install taskforce-cli`) and see every available subcommand
- execute a one-shot mission via `taskforce run mission "..."` (streaming or batch) or enter chat via `taskforce chat`
- boot the REST API + bundled web UI via `taskforce up` (auto-opens the browser when `/health` answers; `--no-browser` for headless)
- boot just the REST API via `taskforce serve` (uvicorn wrapper with `--reload`, `--workers`, `--log-level`)
- start the generic agent daemon via `taskforce daemon start --profile <name> [--role <overlay>]`
- list / inspect tools, skills, profiles, conversations, missions, runtimes, standing goals via the respective subcommand groups
- pick a profile per invocation via `--profile <name>` / `-p <name>` (or persistently via `TASKFORCE_PROFILE`)
- get agent-package subcommands automatically (`taskforce epic`, `taskforce rag`, ...) once the matching package is installed
- get agent-package tools merged into `taskforce tools list` and profiles resolvable via `--profile <name>` with zero CLI code changes
- see which optional agent packages are installed via `taskforce version`

## Invariants (what must always be true)

- The `taskforce` script is contributed by exactly one of two packages: `taskforce-cli` (preferred — the unified CLI) or `taskforce` (fallback when `taskforce_cli` is not importable). Both expose the same top-level command name.
- `--profile <name>` and `-p <name>` flags are accepted at the top level on every subcommand. Per-subcommand `--profile` flags (e.g. `taskforce run mission --profile X`) override the global value.
- Default profile resolution: unified CLI returns `butler` when a `taskforce.config_dirs` entry-point named `butler` is present (i.e. `taskforce-butler` is installed), otherwise `dev`. The framework-only fallback CLI always defaults to `dev`.
- Agent-package CLI subcommands are discovered via the `taskforce.cli_apps` entry-point group at CLI startup. A subcommand declared by an entry-point overrides the hardcoded Phase-1 fallback of the same name.
- A malformed or import-failing `taskforce.cli_apps` / `taskforce.tools` / `taskforce.config_dirs` entry-point logs a structlog warning and is skipped — one broken package never breaks the rest of the CLI.
- A hardcoded Phase-1 fallback (`epic`, `rag`) is only registered if no entry-point of the same name was loaded, and every fallback hit logs `event="hardcoded_agent_fallback"` so the noise points at deletion candidates.
- `register_agent_config_dirs()` runs once during the CLI top-level callback and registers each discovered package's `configs/`, `configs/custom/`, and `configs/roles/` directories with the profile loader, so sub-agent profiles (Butler roles, coding sub-agents) appear in `GET /api/v1/agents` and resolve via `--profile`.
- `.env` files in the current working directory are auto-loaded via `load_dotenv_if_present()` before any subcommand callback executes — both in the unified and the fallback CLI.
- The fallback CLI exposes exactly the always-on framework subcommands (`run`, `chat`, `tools`, `skills`, `config`, `memory`, `missions`, `goals`, `acp`, `runtimes`) but does NOT register `daemon`, `serve`, or `up` — those live in the unified CLI package.
- `taskforce up` polls the `/health` endpoint before opening the browser and only opens it on a 200 response within a 60-second window; failed health checks leave the server running headless rather than killing it.
- `taskforce up` and `taskforce serve` bind to `127.0.0.1` by default; binding to `0.0.0.0` is explicit (`--host 0.0.0.0`) and documented as "put a reverse proxy in front".

## Configuration surface (the command surface operators rely on)

The CLI command surface IS the user's API to the framework. Commands are
grouped by purpose; the per-command flag set lives in `docs/cli.md`.

**Top-level flags (every subcommand):**

- `--profile <name>` / `-p <name>` — select a configuration profile
- `--debug` / `-d` — enable debug output
- `TASKFORCE_PROFILE=<name>` — env-var equivalent of `--profile`

**Always-available framework subcommand groups** (registered by both unified and fallback CLI):

- `taskforce run` — execute missions (`mission`, `skill`, `agent`)
- `taskforce chat` — interactive chat session
- `taskforce tools` — list / inspect / test tools
- `taskforce skills` — list / show / install skills
- `taskforce config` — show resolved config, list profiles
- `taskforce memory` — inspect memory store and wiki
- `taskforce missions` — list templates, list running missions, cancel by request_id
- `taskforce goals` — standing-goal CRUD + `run-now`
- `taskforce acp` — Agent Communication Protocol diagnostics
- `taskforce runtimes` — agent runtime adapter management

**Unified-CLI-only subcommands** (require `taskforce-cli` installed):

- `taskforce up` — boot REST API + web UI + open browser
- `taskforce serve` — boot REST API only (uvicorn wrapper)
- `taskforce daemon` — generic agent daemon (`start`, `stop`, `status`, `logs`)
- `taskforce version` — print framework version + list installed agent packages

**Agent-package-contributed subcommands** (auto-registered via `taskforce.cli_apps` entry-points or Phase-1 hardcoded fallback):

- `taskforce epic` — multi-agent epic orchestration (from `taskforce-coding-agent`)
- `taskforce rag` — RAG agent operations (from `taskforce-rag-agent`)

## Extension points

- `taskforce.cli_apps` entry-point group — agent packages declare `name = "module:typer_app"` to add the `taskforce <name>` subcommand. Loaded eagerly at CLI startup by `taskforce.application.agent_plugin_registry.load_cli_apps()`.
- `taskforce.config_dirs` entry-point group — packages declare `name = "package_module:relpath"` and the unified CLI registers the resolved directory (and its `custom/` + `roles/` children) with the profile loader.
- `taskforce.tools` entry-point group — packages declare `name = "module:ClassName"` and the descriptor is merged into the framework tool registry, surfaced via `taskforce tools list`.
- `taskforce_cli.agent_discovery.register_agent_config_dirs()` — host applications embedding the unified CLI call this once at startup to mirror its profile-loader bootstrap.
- `taskforce_cli.agent_discovery.get_agent_tool_registrations()` — returns the merged (entry-points + Phase-1 fallback) tool descriptor map, intended for consumers that build their own `ToolRegistry`.

## Tests (must exist and pass)

- spec("cli.taskforce_script_works_after_install")
- spec("cli.default_profile_is_butler_when_taskforce_butler_installed")
- spec("cli.default_profile_is_dev_when_taskforce_butler_missing")
- spec("cli.framework_only_fallback_always_defaults_to_dev")
- spec("cli.global_profile_flag_accepted_on_every_subcommand")
- spec("cli.subcommand_profile_flag_overrides_global")
- spec("cli.env_taskforce_profile_used_when_no_flag")
- spec("cli.cli_apps_entry_point_adds_subcommand")
- spec("cli.cli_apps_entry_point_overrides_hardcoded_fallback")
- spec("cli.broken_cli_apps_entry_point_is_skipped_with_warning")
- spec("cli.hardcoded_agent_fallback_logged_when_used")
- spec("cli.config_dirs_registered_during_top_level_callback")
- spec("cli.custom_and_roles_subdirs_registered_for_each_agent_package")
- spec("cli.dotenv_loaded_before_any_subcommand_runs")
- spec("cli.up_polls_health_before_opening_browser")
- spec("cli.up_binds_127_0_0_1_by_default")
- spec("cli.serve_binds_127_0_0_1_by_default")

## Known gaps

- **CLI exit codes are inconsistent across subcommands** — most error paths raise `typer.Exit(1)` regardless of cause (config-not-found, network failure, validation error, user cancel). Shell consumers cannot distinguish recoverable from fatal failures. Tracked in #363.
- **Phase-1 hardcoded fallback in `taskforce_cli.agent_discovery`** is still active for `taskforce_coding_agent` (config dir + `call_agents_parallel` tool) and `taskforce_rag_agent` (config dir + four `rag_*` tools). Each fallback hit logs `event="hardcoded_agent_fallback"`. Will be deleted once both pyprojects ship the matching entry-points. Tracked in #364.
- **`taskforce up` opens the browser even on SSH sessions** unless `--no-browser` is passed — no TTY/`$DISPLAY` heuristic.
- **The fallback CLI silently lacks `daemon`, `serve`, `up`, and agent-package subcommands** — a `taskforce`-only install yields "no such command" rather than a hint to install the unified CLI.
- **No `@pytest.mark.spec` markers exist yet** — Tests section asserts the target, not current state.

## Cross-references

- related_spec: plugins.md (the three entry-point groups the CLI consumes)
- related_spec: profiles.md (the `--profile` flag and default-profile resolution)
- related_spec: api.md (`taskforce up` / `taskforce serve` boot the FastAPI app this spec covers)
- related_spec: agent-daemon.md (`taskforce daemon` is the entry point for the generic daemon)
- adr: ADR-026 (entry-point plugin discovery — primary design)
- adr: ADR-028 (Butler-as-YAML data package, drove default-profile detection via `taskforce.config_dirs`)
- docs: docs/cli.md (user-facing CLI reference with full flag lists)
- commit: 756592b (entry-point-based agent discovery, ADR-026 Phase 1)
