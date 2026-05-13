# ADR-028: Butler as a YAML-only configuration package

**Status:** Accepted
**Date:** 2026-05-13
**Supersedes:** ADR-010 (final), parts of ADR-013, ADR-017

## Context

ADR-026 introduced entry-point-based plugin discovery. ADR-027
promoted the event-driven daemon, supervisor, service, role-loader,
and the generic ``schedule`` / ``reminder`` / ``rule_manager`` tools
into the framework. The user-approved
``~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md`` plan ends
with Phase 4: ``agents/butler/`` ships **zero LoC of Python** and is
described entirely by its YAML configs plus a minimal package shim
required for entry-point resolution.

After Phases 2 and 3 the remaining Python in ``agents/butler/src/``
was a thin Typer-shim CLI (``cli/commands.py``) that delegated every
sub-command to ``taskforce.application.agent_daemon.AgentDaemon``,
plus the matching ``__init__.py`` files. None of that adds any
behaviour the framework's ``taskforce daemon ...`` command doesn't
already provide.

## Decision

Reduce ``agents/butler/`` to:

```
agents/butler/
├── pyproject.toml         # data-only package, entry-points only
├── README.md
├── src/taskforce_butler/__init__.py   # 1-line shim (just __version__)
└── configs/
    ├── butler.agent.md
    ├── custom/*.yaml         # sub-agent configs
    └── roles/*.{agent.md,yaml}
```

### Concrete changes

1. **Delete every other Python file** under
   ``agents/butler/src/taskforce_butler/``. The remaining
   ``__init__.py`` is a 5-line docstring + ``__version__`` so the
   package is importable (required for entry-point resolution) but
   carries no logic.
2. **``pyproject.toml`` is data-only.** No ``[project.scripts]``, no
   ``taskforce.cli_apps`` entry-point. Just
   ``[project.entry-points."taskforce.config_dirs"]`` mapping
   ``butler = "taskforce_butler:configs"``. Hatch's
   ``force-include`` ships ``configs/`` into the wheel under the
   package path so the entry-point resolves identically for editable
   and installed users. Version bump to ``0.3.0``.
3. **Drop the Butler-specific CLI** (``taskforce butler ...``).
   Replaced 1:1 by ``taskforce daemon start --profile butler``
   (introduced in ADR-027). Backwards-compat note in CLAUDE.md and
   ``agents/butler/README.md``.
4. **Stop importing ``taskforce_butler`` for routing.**
   ``cli/src/taskforce_cli/main.py::_detect_default_profile`` now
   asks ``agent_plugin_registry.load_config_dirs()`` whether the
   ``butler`` profile is reachable; if yes it stays the default,
   otherwise ``"dev"``. The hardcoded ``taskforce_butler`` entry in
   ``_AGENT_PACKAGES`` (legacy fallback for config-dir discovery)
   is also removed — Butler ships the entry-point.
5. **Tests** — the few remaining ones that imported butler internals
   were either migrated to framework tests (Phase 2, Phase 3) or
   already deleted as shim tests. No Phase-4 test moves required.

### Clean break

Consistent with the "Clean break" answer in the plan-mode review:
every Phase 2-4 commit removes the moved/deleted code from
``taskforce_butler`` in the same commit. Post-Phase-4:

* ``from taskforce_butler.cli.commands import app`` →
  ``ModuleNotFoundError``.
* ``from taskforce_butler.daemon import ButlerDaemon`` →
  ``ModuleNotFoundError`` (already true after Phase 2).
* ``import taskforce_butler`` still succeeds (the shim package is
  required so the entry-point ``butler =
  "taskforce_butler:configs"`` can locate its data).

## Why not a true zero-Python package

A zero-Python data-only wheel would require either a different
entry-point convention (path-only, not standardised) or a separate
discovery channel for configs. Keeping a 5-line ``__init__.py`` is
the pragmatic answer that:

* preserves Python's standard
  ``importlib.metadata.entry_points`` semantics,
* keeps editable installs (``agents/butler/src/``) and wheel
  installs (``site-packages/taskforce_butler/``) symmetric,
* costs nothing in maintenance.

The user accepted this tradeoff during plan-mode review.

## Alternatives considered

* **Move ``agents/butler/`` into ``src/taskforce/configs/butler/``
  in the framework.** Rejected per the user's architectural
  constraint that **agent configs must live under ``agents/``,
  never under ``src/taskforce/configs/``** — see
  ``~/.claude/projects/.../memory/feedback_agent_configs_location.md``.
* **Keep the butler CLI as a thin alias for ``taskforce daemon
  start --profile butler``.** Rejected per the user's "clean break"
  answer: redirects/wrappers accumulate. The README+ADR migration
  note is sufficient.
* **Mark ``taskforce-butler`` as a meta-package depending only on
  the framework and ``taskforce-google-workspace``, drop the wheel
  build entirely.** Rejected: that would lose the ``configs/`` wheel
  payload — users who ``pip install taskforce-butler`` need the
  YAMLs to land on disk so ``taskforce daemon start --profile butler``
  finds the profile.

## Consequences

* **Positive.** ``agents/butler/`` ships **0 LoC of Python logic**
  (just a 5-line ``__init__.py`` shim required by entry-point
  conventions). Everything that was butler-specific now lives in
  the framework (generic) or ``taskforce-google-workspace``
  (provider-specific).
* **Positive.** The ``taskforce`` CLI no longer hard-codes any
  butler path. Adding/removing/replacing the Butler profile is a
  drop-in operation now — uninstall ``taskforce-butler``, no
  framework changes needed.
* **Positive.** Onboarding example for "how do I build my own
  always-on agent": clone ``agents/butler/``, edit the YAML,
  publish a sibling package — no Python.
* **Breaking.** ``taskforce butler ...`` and the ``taskforce-butler``
  script entry-point are gone. Migration is a 1:1 substitution to
  ``taskforce daemon start --profile butler``.

## Verification

```powershell
# Reduce to YAML-only — verify
uv sync
test ! -e agents/butler/src/taskforce_butler/cli
test ! -e agents/butler/src/taskforce_butler/infrastructure
ls agents/butler/src/taskforce_butler   # only __init__.py

# Boot still works via the generic daemon command
uv run taskforce daemon start --profile butler --work-dir .taskforce-tmp --no-supervisor

# `taskforce butler ...` is gone from the help
uv run taskforce --help     # no "butler" subcommand

# Legacy imports raise ModuleNotFoundError
uv run python -c "import taskforce_butler.cli.commands"
# -> ModuleNotFoundError

# But the shim package + entry-point still resolves the configs dir
uv run python -c "from importlib.metadata import entry_points; print([ep.value for ep in entry_points(group='taskforce.config_dirs') if ep.name == 'butler'])"
# -> ['taskforce_butler:configs']
```

## References

* Plan: ``~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md``
* Phase 4 board item: #247
* Depends on: ADR-026 (entry-point discovery), ADR-027 (generic agent daemon)
* Supersedes: ADR-010 (final), parts of ADR-013 / ADR-017
