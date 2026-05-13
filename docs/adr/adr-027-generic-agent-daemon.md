# ADR-027: Generic agent daemon pattern

**Status:** Accepted
**Date:** 2026-05-13

## Context

ADR-010 ("Event-driven Butler Agent") introduced a Python class
``ButlerDaemon`` that wires the framework's event-driven primitives
(``SchedulerService``, ``FileRuleEngine``, ``EventRouter``,
``EventSourceRegistry``, ``PersistentAgentService``, the proactive
``GoalEvaluatorService`` from ADR-024) onto a profile YAML, and a
companion ``ButlerService`` that owns the resulting lifecycle.

ADR-017 added role specialisation via ``ButlerRoleLoader`` /
``ButlerRole``: a YAML/Markdown overlay that swaps the agent's persona,
sub-agents, tools, event sources and rules at startup.

A standalone ``DaemonSupervisor`` (issue #156) wraps the bare daemon
with watchdog + auto-restart + signal handling for 24/7 use.

All four pieces lived inside the ``taskforce_butler`` package. None of
them have **any** Butler-specific logic — they only know about the
profile YAML they were handed and the framework primitives they
compose. Other agent packages (coding-agent, rag-agent, future plugins)
would need the same wiring, and the user explicitly requested that
``agents/butler/`` be reducible to *YAML config only* — see the planning
session captured in ``~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md``.

## Decision

Promote the four pieces into the framework with class renames and a
single public CLI entry-point:

| Old (in ``taskforce_butler``) | New (in ``taskforce.*``) |
|---|---|
| ``taskforce_butler.daemon.ButlerDaemon`` | ``taskforce.application.agent_daemon.AgentDaemon`` |
| ``taskforce_butler.service.ButlerService`` | ``taskforce.application.agent_service.AgentService`` |
| ``taskforce_butler.daemon_supervisor.DaemonSupervisor`` | ``taskforce.application.daemon_supervisor.AgentDaemonSupervisor`` |
| ``taskforce_butler.role_loader.ButlerRoleLoader`` | ``taskforce.application.agent_role_loader.AgentRoleLoader`` |
| ``taskforce_butler.domain.butler_role.ButlerRole`` | ``taskforce.core.domain.agent_role.AgentRole`` |

Also moved into the framework's native tool registry (no longer
agent-package contributions):

| Old | New (in ``src/taskforce/infrastructure/tools/native/``) |
|---|---|
| ``taskforce_butler.infrastructure.tools.reminder_tool`` | ``taskforce.infrastructure.tools.native.reminder_tool`` |
| ``taskforce_butler.infrastructure.tools.rule_manager_tool`` | ``taskforce.infrastructure.tools.native.rule_manager_tool`` |
| ``taskforce_butler.infrastructure.tools.schedule_tool`` (duplicate) | deleted — framework already shipped its own ``native/schedule_tool.py`` |

### New public CLI

``taskforce daemon start --profile X [--role Y] [--work-dir DIR] [--no-supervisor]``
(in ``src/taskforce/api/cli/commands/daemon.py``) is the canonical
entry-point for running any event-driven agent. ``taskforce butler start``
remains as a thin shortcut for the duration of the Butler→YAML refactor
(it imports the framework ``AgentDaemon`` directly and is removed in
Phase 4).

``taskforce daemon status --profile X`` reads the agent's
``status.json`` from ``{work_dir}/{profile}/status.json``.

### Key API generalisations

* **``AgentDaemon`` status path.** Now writes
  ``{work_dir}/{profile}/status.json`` instead of the previous
  hardcoded ``{work_dir}/butler/status.json``. This means several
  daemons can coexist on the same work directory (e.g. coding-agent
  daemon + butler daemon).
* **``AgentService`` rules-filename.** Now defaults to
  ``"<profile>/rules.json"`` when a profile is supplied, otherwise
  ``"rules.json"``. The hardcoded ``"butler/rules.json"`` is gone.
* **``AgentRoleLoader`` search dirs.** Constructor now takes an
  explicit ``search_dirs: Sequence[Path]`` list rather than the old
  butler-only ``config_dir`` / ``project_dir`` heuristic. ``AgentDaemon``
  populates the list from ``taskforce.application.agent_plugin_registry
  .load_config_dirs()``  → ``<agent_config_dir>/roles/`` plus
  ``{work_dir}/roles/`` for project-local overrides. The legacy
  ``butler_roles/`` directory name is still searched for backwards
  compatibility.
* **``AgentDaemonSupervisor`` factory.** Unchanged in spirit but
  renamed (the ``Agent`` prefix matches its supervised target).
  ``DaemonStalled`` is still re-exported alongside it.

### Clean break (no compatibility shims)

Per the user-approved phasing in the plan file, the move is *atomic*:
the old module paths in ``taskforce_butler`` are deleted in the same
commit, all internal callers are updated to import from
``taskforce.*``, and ``from taskforce_butler.daemon import ButlerDaemon``
raises ``ModuleNotFoundError`` after this change. Phase 1's
hardcoded-fallback discovery (ADR-026) takes care of any straggler
imports from external code.

## Why now

Phase 1 (ADR-026) made plugin discovery entry-point driven, which is
the prerequisite for moving these primitives without breaking Butler's
``taskforce butler ...`` user-facing contract — Butler's CLI app
remains discoverable via its ``taskforce.cli_apps`` entry-point and
its tools resolve through the now-merged registry.

Phase 3 (#246) extracts Google Workspace tools, and Phase 4 (#247)
deletes ``agents/butler/src/`` entirely. Both phases become much
smaller because of this generalisation.

## Alternatives considered

* **Keep ``ButlerDaemon`` Butler-only, add ``CodingAgentDaemon``,
  ``RagAgentDaemon``, etc.** Rejected: identical wiring three times,
  guaranteed drift.
* **Shim layer + deprecation warnings.** Rejected per the
  user-approved "clean break" answer in the plan-mode review.
* **Keep classes as ``Butler...`` but in the framework module path.**
  Rejected: the class names should reflect what they *are*, not where
  they came from.

## Consequences

* **Positive.** Coding-agent and rag-agent can now run as event-driven
  daemons with zero new code. ``agents/butler/src/`` shrinks from
  ~4,350 LoC to a fraction of that after Phases 3 + 4.
* **Positive.** Tests that previously hard-coded
  ``sys.path.insert(...)`` to import ``taskforce_butler.role_loader``
  no longer need the workaround.
* **Negative.** Any external code (none in this repo, but
  hypothetical third-party plugins) that imported from
  ``taskforce_butler.daemon`` / ``service`` / ``role_loader`` /
  ``daemon_supervisor`` breaks. Migration is a single-line import
  swap.

## Verification

```powershell
uv sync
uv run pytest tests/unit/application/test_agent_daemon_supervisor.py -q
uv run pytest tests/unit/application/test_agent_role_loader.py -q
uv run pytest tests/unit/application/test_agent_service_notification_failures.py -q
uv run pytest tests/unit/infrastructure/tools/test_reminder_tool.py -q
uv run taskforce daemon start --profile butler --work-dir .taskforce-tmp --no-supervisor
# wait for .taskforce-tmp/butler/status.json to appear, then Ctrl+C
uv run python -c "from taskforce_butler.daemon import ButlerDaemon"
# expected: ModuleNotFoundError — clean break achieved
```

## References

* Plan: ``~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md``
* Phase 2 board item: #245
* Supersedes parts of: ADR-010, ADR-017
* Depends on: ADR-026 (entry-point plugin discovery)
