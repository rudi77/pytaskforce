# Taskforce Butler — YAML-only configuration package

Butler is a personal-assistant agent profile distributed as **pure
YAML**. All Python implementation lives elsewhere now:

- The event-driven daemon / supervisor / role-loader / service +
  ``schedule`` / ``reminder`` / ``rule_manager`` tools → ``taskforce.*``
  framework core ([ADR-027](../../docs/adr/adr-027-generic-agent-daemon.md)).
- Gmail / Drive / Calendar tools → sibling package
  [`taskforce-google-workspace`](../google-workspace/README.md)
  ([ADR-027](../../docs/adr/adr-027-generic-agent-daemon.md)).
- Provider-agnostic ``authenticate`` tool → framework native.
- CLI commands → framework's generic
  ``taskforce daemon start --profile <name>``
  ([ADR-028](../../docs/adr/adr-028-butler-as-config-only-package.md)).

This package now ships only:

- `configs/butler.agent.md` — main Butler profile
- `configs/custom/*.yaml` — sub-agent configs (pc-agent, research_agent,
  research_specialist, browser-agent)
- `configs/roles/*.{agent.md,yaml}` — role overlays (accountant, personal_assistant)
- `src/taskforce_butler/__init__.py` — 5-line shim required by the
  Python entry-point that points the framework at this configs/ dir.

## Installation

```bash
uv sync                # adds the workspace member to the venv
# or, from a published wheel:
uv pip install taskforce-butler
```

## Usage

```bash
taskforce daemon start --profile butler
taskforce daemon status --profile butler

# With a role overlay
taskforce daemon start --profile butler --role accountant
```

The former ``taskforce butler ...`` and ``taskforce-butler`` script
entry-points are gone — use ``taskforce daemon ...`` instead.

## Why a Python package at all

The Python entry-point convention
(``[project.entry-points."taskforce.config_dirs"]``) requires a
real importable module so the framework can locate the ``configs/``
directory at runtime. The 5-line ``__init__.py`` does exactly that;
no business logic.
