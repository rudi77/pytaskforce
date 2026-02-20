# Agent Skills

Agent Skills are modular capabilities that extend agent functionality with domain-specific expertise. Each skill packages instructions, metadata, and optional resources (scripts, references, assets) that agents can use when relevant to user requests.

Skills are the **unified system** for both background context injection and user-invokable chat commands (`/skill-name`). The former slash-command system has been merged into skills.

## Overview

Skills provide:
- **Domain-specific expertise**: Specialized knowledge and workflows for specific tasks
- **Progressive loading**: Only load what's needed, when it's needed
- **Resource bundling**: Include scripts, references, and asset files
- **Easy extensibility**: Create custom skills as simple directories with SKILL.md files
- **Direct invocation**: PROMPT and AGENT skills can be invoked via `/skill-name [args]` in chat

## Skill Types

Every skill has a `type` field in its YAML frontmatter that controls how it is invoked:

| Type | Value | Invocation | Description |
|------|-------|-----------|-------------|
| **Context** | `context` | Activated via `activate_skill` tool or intent routing | Injects instructions into the system prompt. Default type. |
| **Prompt** | `prompt` | `/skill-name [args]` in chat, or `taskforce run skill <name>` | One-shot prompt template with `$ARGUMENTS` substitution. |
| **Agent** | `agent` | `/skill-name [args]` in chat, or `taskforce run skill <name>` | Temporarily overrides agent config (profile, tools, MCP servers). |

### Context Skill (default)

Activated automatically by the intent router or manually with the `activate_skill` tool. Adds instructions to the system prompt for the current conversation.

```markdown
---
name: pdf-processing
description: Processing PDF files with OCR and layout analysis.
# type: context  ← this is the default, may be omitted
---

# PDF Processing

Always use pdfplumber for layout-aware extraction...
```

### Prompt Skill

Directly invoked by the user via `/skill-name [arguments]`. The `$ARGUMENTS` placeholder in the body is replaced by user-provided text.

```markdown
---
name: code-review
type: prompt
description: Review code for bugs and style. Invoke with /code-review <file>
---

Please perform a thorough code review of the following:

$ARGUMENTS

Focus on bugs, security issues, and readability.
```

**Usage in chat:**
```
/code-review src/main.py
```

### Agent Skill

Temporarily switches the agent to a specialized configuration for one execution.

```markdown
---
name: agents/refactor
type: agent
description: Refactoring agent with deep editing tools.
profile: coding_agent
tools:
  - file_read
  - file_write
  - shell
  - python
---

You are a senior engineer focused on refactoring. Apply SOLID principles.

$ARGUMENTS
```

**Usage in chat:**
```
/agents/refactor clean up the authentication module
```

Agent skill frontmatter supports these extra fields:
- `profile` – profile YAML to load (e.g. `coding_agent`)
- `tools` – list of tool short names to enable
- `mcp_servers` – MCP server configs
- `specialist` – optional specialist prompt override

### Slash Name Override

By default, the skill is invokable under `/<skill-name>`. You can override this:

```yaml
---
name: agents/code-review
slash-name: cr          # Invokable as /cr instead of /agents/code-review
type: prompt
description: Quick code review
---
```

### Hierarchical Names

Skills can be organised in subdirectories. The full name uses `:` as separator:

```
.taskforce/skills/
└── agents/
    ├── reviewer/
    │   └── SKILL.md   → name: agents:reviewer  → /agents:reviewer
    └── architect/
        └── SKILL.md   → name: agents:architect → /agents:architect
```

## Quick Start

### Creating a Skill

Create a directory in `src/taskforce_extensions/skills/` with a `SKILL.md` file:

```bash
mkdir -p src/taskforce_extensions/skills/my-skill
```

Create `src/taskforce_extensions/skills/my-skill/SKILL.md`:

```markdown
---
name: my-skill
description: Brief description of what this skill does and when to use it.
---

# My Skill

Instructions and guidance for the agent when this skill is active.

## Usage

Explain how to use this skill...

## Examples

Provide concrete examples...
```

### Using Skills

Skills are automatically discovered from configured directories. The `SkillService` provides the main interface:

```python
from taskforce.application.skill_service import get_skill_service

# Get the skill service
skill_service = get_skill_service()

# List available skills
skills = skill_service.list_skills()
print(f"Available skills: {skills}")

# Activate a skill
skill_service.activate_skill("my-skill")

# Get combined instructions from active skills
instructions = skill_service.get_combined_instructions()
```

## Skill Structure

### Required Files

Every skill must have a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: skill-name           # Required: lowercase, hyphenated
description: Description   # Required: what and when to use
type: context              # Optional: context (default), prompt, agent
---

# Skill Instructions

The body contains instructions for the agent.
```

### Optional Resources

Skills can include additional files and folders:

```
my-skill/
├── SKILL.md              # Required: metadata and instructions
├── scripts/              # Optional: executable scripts
│   └── helper.py
├── references/           # Optional: reference docs/notes
│   └── README.md
└── assets/               # Optional: static assets
    └── diagram.png
```

### Field Requirements

**name:**
- Maximum 64 characters
- Lowercase letters, numbers, and hyphens only (kebab-case)
- Must match the skill directory name
- Cannot contain `--` or start/end with `-`

**description:**
- Maximum 1024 characters
- Must be non-empty
- Should describe both what the skill does AND when to use it

### Optional Frontmatter

Skills may also include optional YAML frontmatter fields:

**type:**
- Skill execution type: `context` (default), `prompt`, or `agent`

**slash-name** (or `slash_name`):
- Override the `/name` used for chat invocation (defaults to the skill `name`)

**profile:**
- For `agent` type: profile YAML to load (e.g. `coding_agent`)

**tools:**
- For `agent` type: list of tool short names to enable

**mcp_servers:**
- For `agent` type: list of MCP server configurations

**specialist:**
- For `agent` type: optional specialist prompt override

**license:**
- Optional license identifier or short label (e.g., SPDX)

**compatibility:**
- Optional compatibility note (runtime, model, platform)
- Maximum 500 characters

**metadata:**
- Optional key/value metadata for internal tooling
- YAML object or map only

**allowed-tools:**
- Optional space-delimited tool allowlist string

## Progressive Loading

Skills use a three-level loading pattern to minimize context usage:

### Level 1: Metadata (Always Loaded)

Only `name` and `description` from YAML frontmatter. This is loaded at startup for all discovered skills and included in system prompts for skill discovery.

**Token cost:** ~100 tokens per skill

### Level 2: Instructions (Loaded When Triggered)

The full SKILL.md body content. Loaded when a skill is activated based on relevance to user request.

**Token cost:** Typically under 5k tokens

### Level 3: Resources (Loaded As Needed)

Additional files (references/, scripts/, assets/). Loaded only when explicitly referenced during execution.

**Token cost:** Effectively unlimited (loaded on demand)

## Configuration

### Default Skill Directories

Skills are discovered from these default locations:
- `~/.taskforce/skills/` - User-level skills
- `.taskforce/skills/` - Project-level skills
- `src/taskforce_extensions/skills/` - Extension skills

### Custom Directories

Add custom skill directories via the SkillService:

```python
from taskforce.application.skill_service import SkillService

skill_service = SkillService(
    skill_directories=["/path/to/my/skills"],
    extension_directories=["/path/to/extensions"],
)
```

## API Reference

### SkillService

Main interface for skill management:

```python
class SkillService:
    def list_skills(self) -> list[str]:
        """List all available skill names."""

    def list_slash_command_skills(self) -> list[SkillMetadataModel]:
        """List metadata of PROMPT and AGENT type skills (directly invokable)."""

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""

    def activate_skill(self, name: str) -> bool:
        """Activate a CONTEXT skill by name."""

    def deactivate_skill(self, name: str) -> None:
        """Deactivate a skill."""

    def get_active_skills(self) -> list[Skill]:
        """Get currently active skills."""

    def get_combined_instructions(self) -> str:
        """Get combined instructions from active skills."""

    def resolve_slash_command(self, command_input: str) -> tuple[Skill | None, str]:
        """Resolve '/name [args]' input to (skill, arguments) tuple."""

    def prepare_skill_prompt(self, skill: Skill, arguments: str) -> str:
        """Substitute $ARGUMENTS in a PROMPT-type skill."""

    def read_skill_resource(self, skill_name: str, path: str) -> str | None:
        """Read a resource from an active skill."""
```

### Skill Model

```python
@dataclass
class Skill:
    name: str                        # Skill identifier (may be hierarchical: agents:reviewer)
    description: str                 # Trigger description
    instructions: str                # Main content from SKILL.md
    source_path: str                 # Path to skill directory
    skill_type: SkillType            # CONTEXT | PROMPT | AGENT
    slash_name: str | None           # Override for /name invocation
    agent_config: dict | None        # Profile/tools for AGENT type

    @property
    def effective_slash_name(self) -> str:
        """Returns slash_name if set, otherwise name."""

    def substitute_arguments(self, arguments: str) -> str:
        """Replace $ARGUMENTS placeholder in instructions."""

    def get_resources(self) -> dict[str, str]:
        """List available resource files."""

    def read_resource(self, path: str) -> str | None:
        """Read a resource file."""
```

### SkillRegistry

Low-level registry for skill discovery:

```python
class FileSkillRegistry:
    def discover_skills(self) -> list[SkillMetadata]:
        """Discover all available skills."""

    def get_skill(self, name: str) -> Skill | None:
        """Load a skill by name."""

    def list_skills(self) -> list[str]:
        """List skill names."""

    def refresh(self) -> None:
        """Re-scan skill directories."""
```

## Integration with Agents

Skills can be integrated into agent system prompts:

```python
from taskforce.core.prompts import (
    build_system_prompt,
    format_skills_metadata,
    format_active_skills_instructions,
)

# Include skill metadata in prompt for discovery
skills_metadata = skill_service.get_all_metadata()
metadata_section = format_skills_metadata(skills_metadata)

# Include active skill instructions
active_skills = skill_service.get_active_skills()
instructions_section = format_active_skills_instructions(active_skills)

# Build full system prompt
system_prompt = build_system_prompt(
    base_prompt=base_prompt,
    tools_description=tools_desc,
    skills_metadata=metadata_section,
    active_skills=instructions_section,
)
```

## Best Practices

### Writing Skills

1. **Clear descriptions**: Include both what the skill does and when to use it
2. **Structured instructions**: Use headers to organize content
3. **Code examples**: Provide concrete, runnable examples
4. **Resource references**: Link to additional files when appropriate

### Skill Organization

1. **One purpose per skill**: Keep skills focused on a single domain
2. **Consistent naming**: Use descriptive, hyphenated names
3. **Modular resources**: Split large content into multiple files
4. **Documentation**: Include README or REFERENCE files for complex skills

### Performance

1. **Keep metadata light**: Short descriptions minimize always-loaded content
2. **Defer loading**: Put detailed content in the body, not the description
3. **Use resources**: Large reference materials should be separate files

## Example Skills

### Code Review Skill

```markdown
---
name: code-review
description: Review code for bugs, security vulnerabilities, and improvements. Use when the user asks for code review or wants feedback on code quality.
---

# Code Review

Follow this structured approach when reviewing code:

1. **Bug Analysis**: Check for off-by-one errors, null dereferences, resource leaks
2. **Security Review**: Look for injection vulnerabilities, XSS, CSRF
3. **Code Quality**: Evaluate readability, naming, DRY violations
4. **Best Practices**: Check error handling, logging, documentation

## Output Format

```markdown
## Code Review Summary

### Critical Issues
[List critical bugs or security issues]

### Improvements
[Suggested improvements]

### Recommendations
[Actionable next steps]
```
```

### Data Analysis Skill

```markdown
---
name: data-analysis
description: Analyze data, create visualizations, and extract insights. Use when the user wants to analyze datasets, create charts, or understand data patterns.
---

# Data Analysis

## Workflow

1. **Data Understanding**: Inspect structure, types, size
2. **Quality Assessment**: Check missing values, outliers, duplicates
3. **Exploratory Analysis**: Distributions, correlations, patterns
4. **Insights & Reporting**: Summarize findings with visualizations
```

## Security Considerations

- Skills should only be loaded from trusted sources
- Review skill content before using custom skills
- Skills have access to the same capabilities as the agent
- Sensitive data should not be stored in skill files

## Troubleshooting

### Skill Not Discovered

1. Check the skill is in a configured directory
2. Verify SKILL.md has valid YAML frontmatter
3. Ensure name follows validation rules (lowercase, hyphenated)
4. Call `skill_service.refresh()` to re-scan directories

### Skill Validation Errors

Common validation issues:
- Name contains uppercase letters or spaces
- Name does not match the skill directory name
- Name contains `--` or ends with `-`
- Name exceeds 64 characters
- Description is empty or exceeds 1024 characters
- Description contains XML tags

### Resource Not Found

1. Verify the resource file exists in the skill directory
2. Check the path is relative to the skill directory
3. Ensure the skill is active before reading resources
