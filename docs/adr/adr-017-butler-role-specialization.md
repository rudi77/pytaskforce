# ADR-017: Butler Role Specialization

**Status:** Accepted
**Date:** 2026-03-22
**Deciders:** Development Team

## Context

The Butler agent is a 24/7 event-driven daemon that acts as a personal assistant. Currently, it has a hardcoded persona (`BUTLER_SPECIALIST_PROMPT`), a fixed set of sub-agents (pc-agent, research_agent, doc-agent, coding_agent), and a predetermined tool list. This makes it a general-purpose assistant, but users need the ability to specialize the Butler for specific domains — e.g., an accounting assistant, IT support coordinator, or project manager.

The challenge is introducing role specialization without:
- Duplicating infrastructure configuration (persistence, LLM, scheduler, security)
- Breaking backward compatibility for existing deployments
- Adding unnecessary complexity to the startup flow

## Decision

We introduce **Butler Roles** as overlay YAML files that define WHAT the butler is (persona, sub-agents, tools), while the existing butler profile YAML defines HOW it runs (infrastructure configuration).

### Role Definition

A role is a YAML file in `configs/butler_roles/` (package-bundled) or `.taskforce/butler_roles/` (project-local):

```yaml
name: accountant
description: "Accounting assistant for invoice processing and bookkeeping"

persona_prompt: |
  # Accountant Coordinator
  You handle invoices, bookkeeping, and financial reporting.
  {{SUB_AGENTS_SECTION}}

sub_agents:
  - specialist: doc-agent
    description: "Invoice extraction and document processing"
  - specialist: research_agent
    description: "Tax regulation lookup"

tools:
  - memory
  - ask_user
  - calendar
  - schedule
```

### Activation

Roles are activated at startup via CLI option or YAML field:

```bash
taskforce butler start --role accountant
```

Or in `butler.yaml`:
```yaml
role: accountant
```

### Merge Semantics

When a role is loaded, it overlays the base butler config:
- `sub_agents`, `tools`: **REPLACED** (role defines the complete set)
- `event_sources`, `rules`, `mcp_servers`: **APPENDED**
- `system_prompt`: **SET** from `persona_prompt`
- `specialist`: **CLEARED** (role replaces specialist lookup)
- Infrastructure keys: **PRESERVED** from base config

### Key Components

| Component | Layer | Purpose |
|-----------|-------|---------|
| `ButlerRole` | Core/Domain | Frozen dataclass for role data |
| `ButlerRoleLoader` | Application | Load, list, and merge roles |
| `ButlerDaemon` | API | Applies role during config loading |
| Butler CLI | API | `--role` option + `roles list/show` commands |

## Consequences

### Positive

- **Clean separation**: Role (persona) vs. infrastructure (chassis) are independent
- **Easy to create**: Adding a new role = creating one YAML file
- **Backward compatible**: No `role` field = existing behavior preserved exactly
- **Reuses existing mechanisms**: Factory already handles `system_prompt` + `sub_agents`; `{{SUB_AGENTS_SECTION}}` placeholder already works in `SystemPromptAssembler`

### Negative

- Role is fixed at startup (no runtime role switching) — acceptable per requirements
- Role YAML format is another config format to learn — mitigated by examples and CLI `roles show`

## Alternatives Considered

1. **Roles as Skills**: Skills are designed for runtime activation within a running agent. A role changes the entire agent identity at startup — different concern.
2. **Separate butler profiles**: E.g., `butler_accountant.yaml`. Works but duplicates all infrastructure config across every role variant.
3. **Roles as Plugins**: Too heavyweight for just persona + sub-agents. Plugins are for custom code (tools, domain models).
