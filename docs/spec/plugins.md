---
feature: plugins
status: shipped
since: 2026-01-06
last_verified: 2026-05-16
owner: rudi77
adr: ADR-026
---

# Plugin System — Entry-point Discovery of Tools, CLI Apps, and Configs

Taskforce discovers extensions from any installed Python package via three
`importlib.metadata` entry-point groups. Once a package is `pip install`'d,
its tools appear in the framework registry, its Typer apps mount as
`taskforce <name>` subcommands, and its YAML config directories become
resolvable via `--profile`. The same mechanism backs both first-party agent
packages (`taskforce-butler`, `taskforce-coding-agent`, `taskforce-rag-agent`,
`taskforce-google-workspace`) and third-party plugins. A second, REST-facing
plugin protocol (`taskforce.plugins`) lets larger packages contribute
FastAPI middleware, routers, and UI manifests at server startup — that is how
`taskforce-enterprise` overlays multi-tenant auth, admin routes, and the
admin UI.

## Capabilities (what the user can do)

- install an agent package and have its tools appear in `taskforce tools list` without any framework code change
- install an agent package and have its `taskforce <name>` subcommand appear in `taskforce --help`
- install an agent package and resolve its profiles transparently via `--profile <name>`
- ship a third-party plugin that contributes FastAPI middleware + routers via a `taskforce.plugins` entry-point, mounted under `/api/v1`
- ship a third-party plugin that contributes a UI manifest, surfaced at `GET /api/v1/ui/manifest` so the SPA mounts the matching feature module
- disable all entry-point plugin discovery for a process with `TASKFORCE_DISABLE_PLUGINS=1` (used by tests that need a plugin-free runtime)
- load a directory-style plugin ad-hoc via the legacy `PluginLoader.discover_plugin(path)` path (used by `--plugin` and by API auto-discovery of `examples/`)
- override a built-in tool short name by shipping the same name in a `taskforce.tools` entry-point — entry-point wins on collision

## Invariants (what must always be true)

- A malformed entry-point value, a missing target module, or an exception during `ep.load()` is logged as a structlog warning and skipped — one broken plugin never breaks discovery for any other.
- Reading entry-points never imports the contributing package until the entry is actually used (config-dir resolution and tool-descriptor registration import the module; `load_cli_apps` calls `ep.load()` eagerly).
- A tool short name contributed via `taskforce.tools` overrides the framework's built-in registry entry of the same name. No two implementations of one short name coexist in a process.
- Setting `TASKFORCE_DISABLE_PLUGINS` to `1`, `true`, `yes`, or `on` (case-insensitive) makes `discover_plugins()` return an empty list before any plugin code is loaded.
- A `taskforce.plugins` plugin whose `initialize()` raises is recorded with `error` set on its `PluginInfo`, is never added to `get_loaded_plugins()`, and does not contribute middleware or routers.
- `shutdown_plugins()` calls each loaded plugin's `shutdown()` once; exceptions in one plugin's shutdown do not prevent the rest from being shut down.
- A UI manifest getter that raises is logged with traceback and skipped — `GET /api/v1/ui/manifest` still returns the manifests from every well-behaved plugin.
- Config-directory resolution probes `package_dir/relpath`, `package_dir.parent/relpath`, and `package_dir.parent.parent/relpath` in that order, so editable installs (`agents/<name>/src/<pkg>/configs`) and wheel installs both resolve.

## Configuration surface (the profile keys / env vars operators rely on)

Entry-point groups (declared in a contributing package's `pyproject.toml`):

- `[project.entry-points."taskforce.tools"]` — `name = "module.path:ClassName"`. Registered as a tool descriptor with short name `name`, merged on top of the framework's built-in tool registry.
- `[project.entry-points."taskforce.cli_apps"]` — `name = "module.path:typer_app"`. Loaded eagerly and added to the unified CLI as the `taskforce <name>` subcommand.
- `[project.entry-points."taskforce.config_dirs"]` — `name = "package_module:relpath"`. Resolved to a filesystem directory and registered with `ProfileLoader` so `--profile <agent>` resolves YAML inside that directory and its `custom/` and `roles/` subdirectories.
- `[project.entry-points."taskforce.plugins"]` — `name = "module.path:PluginClass"`. Class must satisfy `PluginProtocol` (sync `initialize`, `get_middleware`, `get_routers`, `extend_factory`, `shutdown`; optional `get_ui_manifest`). Loaded at FastAPI app construction time.

Env vars:

- `TASKFORCE_DISABLE_PLUGINS` (default unset) — when `1`/`true`/`yes`/`on`, suppresses every `taskforce.plugins` discovery call for the process. Does **not** affect the three agent-discovery groups above.

Per-plugin config (REST plugins only) is read from the same source the rest of the application uses (env, settings store) and passed to `initialize(config)` via the per-plugin section of `plugin_config`.

## API surface (the contract clients depend on)

- GET /api/v1/ui/manifest → 200 with `{plugins: [UIManifestEntry, ...]}` — one entry per loaded `taskforce.plugins` plugin that implements `get_ui_manifest()` and whose manifest validates. Invalid manifests are dropped, not surfaced as errors.

Plugin-contributed routers register under `/api/v1` with whatever sub-prefix they declare; those endpoints are part of the contributing plugin's spec, not this one.

## Extension points

- `taskforce.tools` (group) — agent packages and third-party plugins register tools by short name.
- `taskforce.cli_apps` (group) — packages contribute Typer subcommands.
- `taskforce.config_dirs` (group) — packages contribute YAML profile directories.
- `taskforce.plugins` (group) — packages contribute REST-layer plugins (middleware + routers + UI manifest).
- `PluginProtocol` in `taskforce.application.plugin_loader` — structural contract for REST plugins.
- `register_tool` / `unregister_tool` in `taskforce.infrastructure.tools.registry` — runtime-only contributions (primarily tests).
- `PluginLoader` in `taskforce.application.plugin_loader` — directory-style plugin loader used by the CLI `--plugin <path>` flag and by API auto-discovery of `examples/` / `plugins/`.

## Tests (must exist and pass)

- spec("plugins.entry_point_tool_appears_in_registry")
- spec("plugins.entry_point_tool_overrides_builtin")
- spec("plugins.entry_point_cli_app_adds_subcommand")
- spec("plugins.entry_point_config_dir_resolves_profile")
- spec("plugins.broken_entry_point_is_skipped_with_warning")
- spec("plugins.disable_env_var_short_circuits_discovery")
- spec("plugins.plugin_initialize_failure_is_isolated")
- spec("plugins.plugin_shutdown_failure_does_not_block_others")
- spec("plugins.ui_manifest_getter_exception_is_skipped")
- spec("plugins.ui_manifest_invalid_payload_is_dropped")
- spec("plugins.config_dir_probes_three_candidate_paths")

## Known gaps

- **`PluginLoader.load_tools` mutates `sys.path`** by inserting the plugin directory and removing it in a `finally` block. Concurrent plugin loads or re-entrant loads can leave the path polluted or remove an entry another loader still needs. Tracked in #343.
- **Phase-1 hardcoded fallback still active in `agent_discovery`** for `taskforce_coding_agent` (config dir + `call_agents_parallel` tool) and `taskforce_rag_agent` (config dir + four `rag_*` tools). Every fallback hit logs `event="hardcoded_agent_fallback"`. The plan is to delete the fallback once both pyprojects ship entry-points. Tracked in #364.
- **`load_tool_descriptors()` imports each contributing module at discovery time** to verify it exists; a heavy import side-effect in a third-party plugin runs once per process even if the tool is never used.
- **Directory-style `PluginLoader` path has no entry-point equivalent for skills** — plugin-bundled skills are picked up only when the plugin is loaded via `--plugin <path>` (which calls `register_skill_dir`), not via entry-point discovery.
- **No backend `@pytest.mark.spec` markers exist yet** — the Tests section above asserts the target, not current state. Spec-check will flag each marker as "asserted but missing test".

## Cross-references

- adr: ADR-026 (entry-point plugin discovery — primary design)
- related_spec: tools.md (the `taskforce.tools` group is the tool-system's plugin entry point)
- related_spec: profiles.md (the `taskforce.config_dirs` group is how packages register profile YAML directories)
- related_spec: cli.md (the `taskforce.cli_apps` group is how packages contribute subcommands)
- related_spec: skills.md (plugin-bundled skills register via `register_skill_dir`)
- docs: docs/plugins.md (user-facing plugin author guide)
- commit: 5661605 (first plugin system, 2026-01-06)
- commit: 756592b (entry-point discovery added, 2026-05-13, ADR-026 Phase 1)
