# Taskforce Butler Agent

Event-driven personal assistant — Google Workspace integration and
butler-specific configs.

After [ADR-027](../../docs/adr/adr-027-generic-agent-daemon.md) the
event-driven daemon, scheduler, rule-engine, supervisor, and role-loader
all live in `taskforce.*` (framework core). Phase 3 (#246) then moved
Gmail / Drive / Calendar into the sibling
[`taskforce-google-workspace`](../google-workspace/README.md) package,
and the provider-agnostic `authenticate` tool joined the framework
native tools. This package now ships:

- `learning_service.py` — post-conversation knowledge extraction.
- A thin CLI shim (`taskforce butler ...`) that delegates to the
  framework's `taskforce daemon ...` command.
- Butler profile + role configs (`configs/butler.agent.md`,
  `configs/custom/*.yaml`, `configs/roles/*.{agent.md,yaml}`).

Phase 4 (#247) reduces this further to a data-only package.

## Installation

```bash
cd agents/butler
uv sync
```

## Usage

Canonical (framework command, profile-agnostic):

```bash
taskforce daemon start --profile butler
taskforce daemon status --profile butler
```

Legacy shortcuts (still work — wrap the framework command):

```bash
taskforce butler start --profile butler
taskforce butler status
taskforce butler rules list
taskforce butler schedules list
taskforce butler roles list
```

## Note

The Butler is being refactored to a YAML-only configuration package
(plan: `~/.claude/plans/ich-will-dass-wir-composed-hanrahan.md`,
phases #244-#247). Phase 2 (this milestone) moved all generic
plumbing into the framework; subsequent phases move Google Workspace
into `taskforce-google-workspace` and finally reduce
`agents/butler/src/` to zero LoC.
