---
feature: skills
status: shipped
since: 2026-01-24
last_verified: 2026-05-16
owner: rudi77
adr: ADR-011
---

# Skills System — Modular Agent Capabilities

Skills are file-based capability bundles (`SKILL.md` + optional resource files)
that extend what an agent can do without writing Python. Each skill declares
one of three execution types — **context** (instructions injected into the
system prompt), **prompt** (one-shot template with `$ARGUMENTS`), or **agent**
(temporary profile override). Skills are discovered from user, project, plugin
and bundled directories, identified by kebab-case names that may use `:` as a
hierarchical separator, and invoked from chat via `/name [args]`, from the CLI
via `taskforce run skill`, or from inside an agent via the `activate_skill`
tool.

## Capabilities (what the user can do)

- drop a `SKILL.md` into `.taskforce/skills/<name>/` or `~/.taskforce/skills/<name>/` and have the next chat session pick it up without restart
- list every discovered skill, grouped by type, via `/skills` in chat or `taskforce skills list`
- filter the CLI listing by type (`taskforce skills list --type context|prompt|agent`)
- invoke a PROMPT skill from chat by typing `/name some arguments` — the body's `$ARGUMENTS` is substituted and sent as the user mission
- invoke an AGENT skill from chat by typing `/name args` — the agent reconfigures itself (profile / tools / mcp_servers / specialist) for that turn
- activate a CONTEXT skill from chat by typing `/name` — its instructions are appended to the system prompt for the rest of the session
- run any skill non-interactively via `taskforce run skill <name> [args...]`
- let the agent itself activate a CONTEXT skill mid-execution via the `activate_skill` tool
- give a skill an alternate slash trigger via `slash-name:` so `/review` can resolve to a longer canonical name
- group skills hierarchically using `:` (e.g. `agents:reviewer` is invoked as `/agents:reviewer`)
- bundle resource files alongside `SKILL.md` (scripts, templates, references) and read them at runtime via the skill's source directory
- restrict a skill to a subset of tools via the `allowed-tools` frontmatter (a space-delimited allowlist)
- preview a skill (frontmatter + body) from the REST API for UI rendering

## Invariants (what must always be true)

- A skill's `name` must be valid kebab-case (optionally with `:` hierarchy), max 64 characters, lowercase only. Invalid names fail to load.
- The last `:`-separated segment of a skill's `name` must equal its containing directory name. Mismatched skills fail to load and are logged as parse errors.
- `description` is required and non-empty (max 1024 chars); missing description fails parsing.
- Only PROMPT and AGENT skills appear in `list_slash_command_skills` — CONTEXT skills are listed but not "directly invokable" in the same sense (typing `/name` activates them rather than running them).
- `effective_slash_name` is `slash-name` if set, otherwise `name`. Slash-name lookup is case-insensitive.
- Skill loading is progressive: metadata (frontmatter only) at discovery time, full instructions + workflow + resources on first `get_skill`. Resource lists are cached per skill instance.
- A skill load failure (bad YAML, validation error, missing fields) never crashes discovery — the affected skill is skipped and logged; the rest stay available.
- `activate_skill` from the agent auto-refreshes the registry once if the requested skill is not found, so a skill created mid-session via `file_write` becomes usable on the next call.
- The chat `/skills` listing and `/name` resolution see the same registry as the REST `/api/v1/skills` endpoints — both go through the singleton `SkillService`.
- Directory edits (new files, modified `*.md` mtimes, additions via `register_skill_dir`) are picked up automatically on the next REST list/get call without an explicit refresh — but only inside directories the registry already knows about.

## API surface (the contract clients depend on)

- GET  /api/v1/skills → 200 with `{skills: [...]}` sorted alphabetically by name
- GET  /api/v1/skills/{name} → 200 with frontmatter fields plus the SKILL.md body
- GET  /api/v1/skills/{name} → 404 if no skill with that canonical name is discovered

Write endpoints (POST/PUT/DELETE) are intentionally not in the framework spec — they live in the enterprise plugin where they carry audit + permission semantics (see ADR-022 §6).

## Configuration surface (the profile keys / env vars operators rely on)

Skill discovery is location-driven rather than profile-driven. The framework searches, in priority order:

- plugin-specific `skills/` directory (when the agent is loaded from a plugin manifest)
- `<project_root>/.taskforce/skills/` and `<project_root>/.claude/skills/` (when the conversation is scoped to a CoWork project)
- `.taskforce/skills/` in the current working directory (legacy fallback, only when no project scope)
- `~/.taskforce/skills/` (per-user, applied across all projects)
- additional directories registered via `taskforce.application.skill_service.register_skill_dir(path)`
- bundled framework skills under `src/taskforce/skills/` (added by the CLI when run from a checkout)

Frontmatter keys consumed by the parser:

- `name:` (required) — canonical skill name; must match directory name (last `:`-segment)
- `description:` (required) — shown in `/skills`, the system prompt, and the UI catalog
- `type:` (default `context`) — one of `context`, `prompt`, `agent`
- `slash-name:` / `slash_name:` — optional alias for `/name` invocation
- `allowed-tools:` / `allowed_tools:` — space-delimited tool allowlist enforced by the active skill
- `license:`, `compatibility:`, `metadata:` — informational
- `profile:`, `tools:`, `mcp_servers:`, `specialist:` — AGENT-type config override (collected into `agent_config`)
- `workflow:` — optional deterministic step sequence or `engine` + `callable_path` for external workflow runners

## Extension points

- `taskforce.application.skill_service.register_skill_dir(path)` — host applications and plugins register additional skill directories at startup. If a singleton `SkillService` already exists, the directory is registered live and a refresh is triggered.
- `taskforce.application.skill_service.set_skill_dir_provider(provider)` — dynamic per-request skill directories (e.g. tenant-scoped enterprise plugin). Resolved on every `refresh_dynamic_skill_dirs()` call.
- `taskforce.application.skill_service.set_writable_skill_root_provider(provider)` — overrides the root under which API-created skills are stored.
- `SkillRegistryProtocol` in `core/interfaces/skills.py` — replaceable skill discovery backend (default `FileSkillRegistry`).
- `SkillProtocol` / `SkillContextProtocol` — alternate skill object / context implementations.

## Tests (must exist and pass)

- spec("skills.invalid_name_rejected")
- spec("skills.directory_name_mismatch_rejected")
- spec("skills.missing_description_rejected")
- spec("skills.context_skill_activated_via_slash")
- spec("skills.prompt_skill_substitutes_arguments")
- spec("skills.agent_skill_overrides_profile")
- spec("skills.slash_name_override_resolves")
- spec("skills.hierarchical_colon_name_resolves")
- spec("skills.discovery_skips_broken_skill")
- spec("skills.activate_skill_auto_refreshes_registry")
- spec("skills.rest_list_returns_sorted")
- spec("skills.rest_get_unknown_returns_404")
- spec("skills.cli_list_filters_by_type")
- spec("skills.mtime_change_triggers_reload_on_next_list")

## Known gaps

- **Skill loader has no schema validation** beyond a handful of frontmatter type checks. Unknown frontmatter keys are silently dropped; malformed `workflow.steps` entries fail at execution time rather than load time. Tracked in #294.
- **Chat slash commands are not sanitised** — `/name args` arguments are substituted into the prompt body verbatim, so a malicious skill author could craft `$ARGUMENTS` placement that lets a user prompt-inject the system prompt. Tracked in #297.
- **`taskforce run skill` does not enforce the skill's `allowed-tools` allowlist** at the CLI level — only the SkillManager-driven path respects it. A skill that should be restricted to `file_read` is run with the profile's full tool set when invoked from the CLI. Tracked in #300.
- **`SkillManager` duplicates state that `core/domain/skill.py::SkillContext` already models** (active skill, switch history). The two paths can diverge — agent-internal activation via `SkillManager` and SkillService-level activation are not transactionally consistent. Tracked in #367.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state. Spec-check will flag each marker as "asserted but missing test".
- **Workflow checkpoint/resume** referenced in `activate_skill_tool` was moved to agent packages — the framework stub raises `NotImplementedError`. Skills with `waiting_for_input` workflows fail at runtime in the framework-only install.

## Cross-references

- adr: ADR-011 (unified skills — primary design)
- related_spec: tools.md (the `activate_skill` and `fetch_result` tools that drive in-agent skill activation)
- related_spec: plugins.md (plugins ship `skills/` directories registered via `register_skill_dir`)
- related_spec: profiles.md (AGENT-type skills override profile-level settings)
- docs: docs/features/skills.md (user-facing guide)
- commit: a7b6d29 (introduced 2026-01-24)
- commit: 93b9e0e (epic-21 unified slash commands and skills, 2026-02-20)
