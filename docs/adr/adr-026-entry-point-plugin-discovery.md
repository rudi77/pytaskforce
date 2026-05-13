# ADR-026: Entry-point-based plugin discovery

**Status:** Accepted
**Date:** 2026-05-13

## Context

The unified `taskforce` CLI and the framework's tool registry both
need to know what each installed agent package contributes —
sub-commands, tool short-names, and config directories. Until now the
wiring was hardcoded in three places:

1. `cli/src/taskforce_cli/main.py:52-73` — three explicit
   `try/import/add_typer` blocks for `taskforce_butler`,
   `taskforce_coding_agent`, `taskforce_rag_agent`.
2. `cli/src/taskforce_cli/agent_discovery.py:27-31` — module-level
   `_AGENT_PACKAGES` list of `(package_name, configs_relpath)` tuples.
3. `cli/src/taskforce_cli/agent_discovery.py:134-167` and
   `src/taskforce/infrastructure/tools/registry.py:200-237` — hardcoded
   tool-descriptor blocks pointing at modules inside the agent packages.

Adding a new agent package, splitting the Butler package (Phases 2-4 of
the Butler → YAML refactor — see plan
`~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md`), or just
moving Google-Workspace tools into a sibling package all require
editing every one of those locations. That is friction we want gone
before the Butler refactor touches the same files in three subsequent
phases.

## Decision

Discover agent-package contributions through **Python entry-points**
read with `importlib.metadata.entry_points`. Three groups, each owned
by a small loader in
`src/taskforce/application/agent_plugin_registry.py`:

| Group | Value form | Loader | Consumer |
|-------|------------|--------|----------|
| `taskforce.tools` | `"module.path:ClassName"` | `load_tool_descriptors()` | merged into `_BUILTIN_REGISTRY` by `tool_registry._resolved_registry` (LRU-cached, invalidated by `register_tool`/`unregister_tool`) |
| `taskforce.cli_apps` | `"module.path:typer_app"` | `load_cli_apps()` | iterated in `cli/src/taskforce_cli/main.py` and passed to `app.add_typer` |
| `taskforce.config_dirs` | `"package_module:relpath"` | `load_config_dirs()` | merged with the legacy `_AGENT_PACKAGES` probe in `agent_discovery.get_agent_config_dirs` |

`iter_entry_points(group)` is the single wrapper around
`importlib.metadata.entry_points`. It catches every metadata-level
exception (corrupt wheels, partial installs) and yields nothing — so a
broken plugin can never crash CLI startup.

Each loader does the obvious thing for its group, with one shared
principle: **fail loudly into structlog, fail safely at runtime**. A
malformed entry-point value, a missing target module, or a
`ep.load()` exception emits a `structlog.warning` and is skipped. The
remaining entries are still returned.

### Transition strategy

The hardcoded paths are not removed in this ADR — they become a
**fallback** so Phase 1 ships zero behavioural change:

* `tool_registry._resolved_registry()` starts with `_BUILTIN_REGISTRY`
  (still containing the legacy butler/rag entries) and merges entry-
  point descriptors on top. Entry-point entries win on overlap.
* `agent_discovery.get_agent_config_dirs()` reads entry-points first,
  then probes `_AGENT_PACKAGES` for any package that did not register
  via entry-points.
* `agent_discovery.get_agent_tool_registrations()` mirrors the same
  pattern.
* `cli/main.py` iterates `load_cli_apps()` first, then falls back to
  the previous import-and-add-typer pattern for known names not yet
  covered.

Every fallback hit logs `event="hardcoded_agent_fallback"` with a
`hint` pointing at the pyproject.toml that should declare the entry-
point. The eventual Phase-4 cleanup is a single `grep` for that event
name.

## Why entry-points

* **Stdlib only** — no extra dependency, works the same in any
  install (`pip`, `uv pip`, editable, wheel).
* **Decoupled discovery** — neither the framework nor the CLI need to
  import the agent package to know it exists; metadata is enough.
* **Standard pattern** — `pytest`, `click`, `gunicorn`, every modern
  Python plugin system uses entry-points. Future plugin authors don't
  need a project-specific manual.
* **Survives renames** — moving `email_tool.py` from
  `taskforce_butler` to `taskforce_google_workspace` (Phase 3) is two
  lines in two `pyproject.toml` files, zero framework changes.

## Alternatives considered

* **Keep the hardcoded registry, expand it.** Rejected: every
  Butler-refactor phase would touch the same three files.
* **Custom plugin manifest (e.g. `taskforce.yaml`).** Rejected:
  bespoke format, needs custom discovery code, harder for plugin
  authors to wire correctly.
* **`setuptools`-only `entry-points.txt`.** Subset of `importlib.metadata`
  but locks us to `setuptools`. Hatchling already writes
  pyproject-style entry-points to wheel metadata, so the modern
  approach is portable.

## Consequences

* **Positive.** Adding a new agent contribution becomes a two-line
  `pyproject.toml` edit, no framework changes needed. Phase 2-4 of
  the Butler refactor become much smaller because each phase only
  has to touch the entry-point declarations, not the discovery wiring.
* **Positive.** Tests can monkeypatch `iter_entry_points` to inject
  synthetic plugins, replacing the old "install the package first"
  testing pattern.
* **Neutral.** A small `lru_cache` was added to the tool registry so
  the entry-point scan runs once per process. `register_tool` /
  `unregister_tool` now invalidate the cache.
* **Negative.** During the transition there are two discovery paths
  (entry-point + hardcoded fallback) which is briefly more code than
  either alone. The `hardcoded_agent_fallback` warnings make the
  finish line visible.

## Implementation notes

* `taskforce.application.agent_plugin_registry` is the only home for
  the wrapper logic. Importing it from elsewhere is fine.
* The three group names are exported as `GROUP_TOOLS`,
  `GROUP_CLI_APPS`, `GROUP_CONFIG_DIRS` constants so callers don't
  hardcode the strings.
* The `config_dirs` resolver probes three candidate paths
  (`package_dir / relpath`, `package_dir.parent / relpath`,
  `package_dir.parent.parent / relpath`) so editable installs of
  `agents/<name>/src/taskforce_<name>` keep working.
* `Phase 4` of the Butler refactor deletes the fallback paths +
  hardcoded blocks once every agent ships entry-points.

## Verification

```powershell
uv sync
uv pip install -e agents/butler -e agents/coding-agent -e agents/rag-agent
uv run taskforce --help                       # butler/epic/rag subcommands visible
uv run taskforce tools list                   # gmail/calendar/rag_* resolve
uv run pytest tests/unit/application/test_agent_plugin_registry.py -q
```

## References

* Plan: `~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md`
* Board: #244 (Phase 1)
* Supersedes / extends: ADR-023 (host integration API) — the new
  entry-point groups become the canonical extension point that ADR-023's
  `register_tool` / `register_profile_dir` helpers can target.
