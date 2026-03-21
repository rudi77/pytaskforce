# Hexagonal review scratchpad

## Files inspected so far
- src/taskforce/core/interfaces/__init__.py
- src/taskforce/core/domain/agent.py
- src/taskforce/application/__init__.py
- src/taskforce/infrastructure/__init__.py

## Initial observations
- core.interfaces exposes protocols for state, LLM, messaging, runtime, skills, tools, gateways, sub-agents.
- core.domain.agent.py is a thin public import path for `taskforce.core.domain.lean_agent.Agent`.
- application and infrastructure package initializers are empty docstring-only modules.
- Need inspect actual domain/application/infrastructure submodules and package layout.
