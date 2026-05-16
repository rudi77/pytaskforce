---
feature: profiles
status: shipped
since: 2026-01-02
last_verified: 2026-05-16
owner: rudi77
---

# Profile System — Agent Configuration & Visibility

A *profile* is a named bundle of agent configuration (system prompt, tools,
MCP servers, planning strategy, persistence, LLM model aliases, ...) that
the user selects at startup with `--profile <name>` or `TASKFORCE_PROFILE=<name>`.
Profiles live as either flat YAML (`<name>.yaml`) or markdown with YAML
frontmatter (`<name>.agent.md`). The framework ships a small set; installed
agent packages contribute their own via entry-points, and a deployment
manifest decides which of the resulting agents surface in the catalog the
UI shows the user.

## Capabilities (what the user can do)

- author a profile as flat YAML (`<name>.yaml`) or as markdown with frontmatter (`<name>.agent.md`) where the markdown body becomes the system prompt
- inherit common settings via `extends: [<preset>, ...]` resolved against `configs/presets/`
- override individual settings on top of the framework `defaults.yaml` baseline
- select a profile per invocation via `taskforce ... --profile <name>` or persistently via `TASKFORCE_PROFILE=<name>`
- drop project-local profiles under `<repo>/agents/<pkg>/configs/` (when developing) or have them auto-discovered from an installed agent package
- let installed agent packages contribute their `configs/` directory through the `taskforce.config_dirs` entry-point group, so `--profile butler` resolves once `taskforce-butler` is installed
- list every discovered profile from the framework + installed packages via `taskforce config profiles`
- restrict which agents the UI Agents page / `GET /api/v1/agents` shows via `src/taskforce/configs/deployment.yaml`
- override that manifest at runtime via `TASKFORCE_DEPLOYMENT_MANIFEST=/path/to/your.yaml`
- override the manifest per tenant from a plugin via `set_deployment_manifest_override(...)`
- override the manifest from the UI via the `visible_agents` section of the settings store, which beats the YAML default
- bypass the manifest filter as a power user via `GET /api/v1/agents?include_hidden=true`

## Invariants (what must always be true)

- The unified CLI's default profile is `butler` when `taskforce_butler` is importable, otherwise `dev`; the framework-only fallback CLI always defaults to `dev`.
- A profile lookup probes, in order: `<dir>/<name>.agent.md`, `<dir>/<name>.yaml`, `<dir>/custom/<name>.agent.md`, `<dir>/custom/<name>.yaml`. The first hit wins. The same sequence runs in the framework dir first, then in every registered extra dir, in registration order.
- For `.agent.md` files the resolved config is built by: framework `defaults.yaml` → each `extends:` preset in left-to-right order → frontmatter → `technical:` block flattened onto the top level → markdown body assigned to `system_prompt` (unless frontmatter explicitly set one).
- An unknown profile raises `FileNotFoundError` with the list of directories that were searched, so misconfiguration is loud, not silent.
- Profile validation failures against the Pydantic schema log a warning but do NOT reject the profile — the framework continues with the unvalidated dict.
- An agent NOT on the deployment manifest stays fully loadable by id (sub-agent extension via `get_agent(...)` is unaffected); it just doesn't appear in user-facing listings.
- When the settings store carries a non-empty `visible_agents.agents` list, it beats the shipped `deployment.yaml`. When neither source supplies a manifest, the registry falls back to its legacy unfiltered behaviour.
- The same profile name appearing in multiple search directories resolves to the first hit; subsequent definitions are shadowed (matching the load-order semantics used by listings).
- The `persistence.type` value during plugin-config merging always comes from the base profile — plugins cannot swap storage backends behind the user's back.
- Reserved basenames `defaults`, `llm_config`, `pricing` are excluded from profile discovery even when files with those names exist in a searched directory.

## API surface (the contract clients depend on)

- GET  /api/v1/agents → 200 with the visible-agents set per active deployment manifest
- GET  /api/v1/agents accepts `include_hidden=true` to bypass the manifest filter
- GET  /api/v1/agents/{agent_id} → 200 for any loadable agent (manifest does not gate by-id lookup)
- GET  /api/v1/agents/{agent_id} → 404 when no profile/custom/plugin agent matches

## Configuration surface (the profile keys / env vars operators rely on)

Profile selection:

- `TASKFORCE_PROFILE=<name>` — override the default profile
- `--profile <name>` — per-invocation override on every CLI subcommand
- `TASKFORCE_DEPLOYMENT_MANIFEST=/path/to/your.yaml` — point at an alternate manifest

Top-level profile keys consumed by the loader and downstream factory:

- `profile: <name>` — informational id (matches filename for discoverability)
- `extends: <preset> | [<preset>, ...]` — preset references resolved under `configs/presets/`
- `technical: {...}` — block that gets flattened onto the top level after merging
- `agent.planning_strategy`, `agent.planning_strategy_params`, `agent.max_steps` — see react-loop spec
- `persistence.type` (`file` | `postgres`), `persistence.work_dir`
- `llm.config_path`, `llm.default_model`
- `logging.level`, `logging.format`
- `context_policy.{max_items,max_chars_per_item,max_total_chars}`
- `tools: [<short_name>, ...]` — resolved against the tool registry
- `mcp_servers: [...]`, `acp: {server, peers, message_bus}`
- `runtime: <name>` (default `taskforce`) — runtime adapter selector
- `system_prompt: <str>` — explicit override; if absent and the file is `.agent.md`, the body becomes the system prompt

Deployment manifest schema (`src/taskforce/configs/deployment.yaml`):

- `version: 1`
- `visible_agents: [<agent_id>, ...]` — allowlist surfaced in catalog listings

Settings-store section (`VISIBLE_AGENTS`):

- `{agents: [<agent_id>, ...]}` — UI-managed override that wins over `deployment.yaml`

## Extension points

- `taskforce.config_dirs` entry-point group — installed agent packages declare `name = "module:relpath"` to add their `configs/` directory to the profile loader's search path (ADR-026).
- `taskforce.application.profile_loader.register_config_dir(path)` — host applications register additional profile directories at startup; called by `taskforce_cli.agent_discovery.register_agent_config_dirs()` for each discovered package.
- `taskforce.application.infrastructure_overrides.set_deployment_manifest_override(provider)` — plugin code (e.g. `taskforce-enterprise`) supplies a per-tenant manifest that beats both the settings store and the YAML default.
- `taskforce.application.infrastructure_overrides.set_agent_registry_override(provider)` — replace the entire agent-registry implementation (used by the enterprise overlay for tenant-scoped Postgres-backed registries).
- `configs/presets/<name>.yaml` — shared snippets referenced via `extends:`; resolved against the same dir-set the loader uses for profiles.

## Tests (must exist and pass)

- spec("profiles.unknown_profile_raises_filenotfound")
- spec("profiles.agent_md_body_becomes_system_prompt")
- spec("profiles.extends_chain_applies_left_to_right")
- spec("profiles.technical_block_flattens_onto_top_level")
- spec("profiles.defaults_yaml_applied_as_baseline")
- spec("profiles.custom_subdir_probed_after_root")
- spec("profiles.extra_config_dirs_probed_after_framework_dir")
- spec("profiles.entry_point_packages_register_config_dirs")
- spec("profiles.schema_validation_failure_warns_does_not_reject")
- spec("profiles.deployment_manifest_filters_list_agents")
- spec("profiles.include_hidden_query_bypasses_manifest")
- spec("profiles.hidden_agent_still_loadable_by_id")
- spec("profiles.settings_store_visible_agents_beats_yaml")
- spec("profiles.missing_manifest_falls_back_to_unfiltered")
- spec("profiles.plugin_cannot_override_persistence_type")
- spec("profiles.cli_default_is_butler_when_installed_else_dev")

## Known gaps

- **No public registry for runtime/planning-strategy plugins**: profiles can declare `runtime:` or `agent.planning_strategy:` but only values wired into the factory resolve — plugins cannot add new ones without forking. See react-loop spec Known gaps.
- **Profile-schema validation is advisory only**: a typo'd top-level key is logged at WARNING and silently kept, so `pythons` instead of `python` in the default profile passes validation and fails only at tool-build time. Tracked indirectly via the wider Pydantic-strict initiative; `src/taskforce/configs/default.yaml` currently contains exactly this typo.
- **Accountant custom profile hardcodes Windows paths** without env-var indirection — `agents/butler/configs/custom/accountant.yaml` is not portable. Tracked in #359.
- **`TopicDetector` confidence threshold is hardcoded** with no profile- or env-override — a profile cannot tune routing aggressiveness today. Tracked in #368.
- **RAG profile tool names are not validated** at load time — `agents/rag-agent/configs/rag_agent.yaml` references `llm` and rag tools whose existence is only checked at tool-build time. Tracked in #360.
- **Plugin-installed agent registries may ignore the deployment manifest**: the route detects whether `list_agents` accepts `include_hidden` and falls back to a positional call, so registries that don't honour the manifest are silently unfiltered.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.

## Cross-references

- related_spec: react-loop.md (`agent.planning_strategy` and friends)
- related_spec: tools.md (the `tools:` list resolves through the tool registry)
- related_spec: plugins.md (the `taskforce.config_dirs` entry-point group)
- related_spec: skills.md (AGENT-type skills temporarily override profile settings)
- adr: ADR-026 (entry-point plugin discovery)
- adr: ADR-027 / ADR-028 (Butler-as-YAML — the canonical case for agent-package-shipped configs)
- docs: docs/profiles.md (user-facing reference)
- docs: docs/agent-config-format.md (`.agent.md` vs flat-YAML format)
- commit: 318b96d (introduced `profile_loader.py`)
- commit: cc1b35f (introduced the deployment manifest, 2026 issue #181)
- commit: 756592b (entry-point-based agent discovery, ADR-026)
