# Agent Skills

Agent Skills are modular capabilities that extend agent functionality with domain-specific expertise. Each skill packages instructions, metadata, and optional resources (scripts, references, assets) that agents can use when relevant to user requests.

## Overview

Skills provide:
- **Domain-specific expertise**: Specialized knowledge and workflows for specific tasks
- **Progressive loading**: Only load what's needed, when it's needed
- **Resource bundling**: Include scripts, references, and asset files
- **Easy extensibility**: Create custom skills as simple directories with SKILL.md files

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

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""

    def activate_skill(self, name: str) -> bool:
        """Activate a skill by name."""

    def deactivate_skill(self, name: str) -> None:
        """Deactivate a skill."""

    def get_active_skills(self) -> list[Skill]:
        """Get currently active skills."""

    def get_combined_instructions(self) -> str:
        """Get combined instructions from active skills."""

    def read_skill_resource(self, skill_name: str, path: str) -> str | None:
        """Read a resource from an active skill."""
```

### Skill Model

```python
@dataclass
class Skill:
    name: str                    # Skill identifier
    description: str             # Trigger description
    instructions: str            # Main content from SKILL.md
    source_path: str             # Path to skill directory

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
