# Butler Roles

Butler Roles allow you to specialize the Butler agent for a specific domain or purpose — e.g., an accounting assistant, IT support coordinator, or project manager.

A role defines WHAT the butler is (persona, sub-agents, tools), while the butler profile defines HOW it runs (persistence, LLM, scheduler, security).

## Quick Start

```bash
# List available roles
taskforce butler roles list

# Show role details
taskforce butler roles show accountant

# Start butler with a specific role
taskforce butler start --role accountant
```

## Built-in Roles

| Role | Description |
|------|-------------|
| `personal_assistant` | General-purpose assistant (mirrors default butler behavior) |
| `accountant` | Accounting assistant for invoice processing and bookkeeping |

## Creating a Custom Role

### Interactive (recommended)

Use the built-in skill to create a role interactively:

```
/create-role Buchhalter für tägliche Belegverarbeitung
```

The Butler will guide you through defining name, persona, sub-agents, tools and save the YAML file.

### Manual

Create a YAML file in one of these locations:

1. `src/taskforce/configs/butler_roles/{name}.yaml` — package-bundled (for shared/default roles)
2. `.taskforce/butler_roles/{name}.yaml` — project-local (for project-specific roles)

### Role YAML Structure

```yaml
# Required
name: my_role
description: "Short description of what this role does"

# Persona prompt — defines the butler's identity and behavior.
# Use {{SUB_AGENTS_SECTION}} placeholder for dynamic sub-agent list.
persona_prompt: |
  # My Role Coordinator

  You are a specialized assistant for [domain].
  You delegate work to specialists and synthesize results.

  ## Specialist routing

  {{SUB_AGENTS_SECTION}}

  ## Rules
  - Be precise
  - Follow domain conventions

# Sub-agents available to this role.
# Each must have a matching config in configs/custom/{specialist}.yaml
sub_agents:
  - specialist: doc-agent
    description: "Document extraction and processing"
  - specialist: research_agent
    description: "Web research and fact checking"

# Tools available to this role (short names from tool registry).
tools:
  - memory
  - send_notification
  - ask_user
  - activate_skill
  - calendar
  - schedule
  - type: parallel_agent
    profile: butler
    max_concurrency: 2

# Optional: additional event sources (appended to base config)
event_sources: []

# Optional: additional trigger rules (appended to base config)
rules: []

# Optional: additional MCP servers (appended to base config)
mcp_servers: []
```

### Merge Semantics

When a role is activated, it overlays the base `butler.yaml`:

| Field | Behavior | Rationale |
|-------|----------|-----------|
| `sub_agents` | **REPLACED** | Role defines the complete agent team |
| `tools` | **REPLACED** | Role defines the complete tool set |
| `system_prompt` | **SET** from `persona_prompt` | Role defines the identity |
| `event_sources` | **APPENDED** | Base + role-specific sources |
| `rules` | **APPENDED** | Base + role-specific rules |
| `mcp_servers` | **APPENDED** | Base + role-specific servers |
| Infrastructure | **PRESERVED** | persistence, LLM, scheduler, security come from butler.yaml |

## Activation Methods

### CLI Option (recommended)

```bash
taskforce butler start --role accountant
```

The `--role` option takes precedence over the YAML `role:` field.

### butler.yaml Field

```yaml
# In butler.yaml
role: accountant
```

### No Role (backward compatible)

If no `role` is specified (neither CLI nor YAML), the butler uses the built-in `BUTLER_SPECIALIST_PROMPT` with hardcoded sub-agents — exactly as before.

## Example: Accountant Role

```yaml
name: accountant
description: "Buchhalter-Assistent für Belegverarbeitung und Kontierung"

persona_prompt: |
  # Buchhalter-Koordinator

  Du bist ein Buchhalter-Assistent. Du unterstützt bei der täglichen
  Buchhaltungsarbeit: Belegerfassung, Kontierung, USt-Prüfung.

  ## Specialist routing

  {{SUB_AGENTS_SECTION}}

  ## Kern-Workflow

  Für jeden Beleg:
  1. Extraktion (doc-agent)
  2. Pflichtangaben-Prüfung (§14 UStG)
  3. Kontierung (SKR03/SKR04)
  4. Routing (auto-buchen oder Rückfrage)

sub_agents:
  - specialist: doc-agent
    description: "Belegextraktion und Dokumentanalyse"
  - specialist: research_agent
    description: "USt-IdNr-Validierung und Steuerrecht-Recherche"

tools:
  - memory
  - send_notification
  - ask_user
  - calendar
  - schedule
  - reminder
  - activate_skill
  - type: parallel_agent
    profile: butler
    max_concurrency: 2
```

## Architecture

See [ADR-017: Butler Role Specialization](../adr/adr-017-butler-role-specialization.md) for the design rationale.

### Component Overview

```
ButlerRole (core/domain)          ← pure dataclass, no dependencies
    ↑
ButlerRoleLoader (application)    ← loads YAML, creates ButlerRole, merges config
    ↑
ButlerDaemon (api)                ← calls role loader during config loading
    ↑
Butler CLI (api/cli)              ← --role option, roles list/show commands
```
