"""Taskforce Butler — YAML-only configuration package (ADR-028).

This package no longer contains any Python implementation. Phases 1-4
of the Butler -> YAML refactor moved everything butler-related into
the framework or a sibling package:

* Daemon + service + role-loader  -> ``taskforce.application.*``        (Phase 2, ADR-027)
* schedule / reminder / rule_manager tools -> ``taskforce.infrastructure.tools.native`` (Phase 2)
* gmail / drive / calendar tools  -> ``taskforce_google_workspace.*``   (Phase 3, ADR-027)
* authenticate tool               -> ``taskforce.infrastructure.tools.native.auth_tool`` (Phase 3)
* CLI subcommands                 -> ``taskforce daemon ...``           (Phase 2, framework command)

What's left is the ``configs/`` directory next to this module — the
Butler profile, sub-agent configs, and role overlays. The
``taskforce.config_dirs`` entry-point in ``pyproject.toml`` makes them
discoverable to the framework.

Run Butler as ``taskforce daemon start --profile butler``.
"""

__version__ = "0.3.0"
