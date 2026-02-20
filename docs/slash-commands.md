# Slash Commands

> **Note:** Slash commands have been unified into the Skills system as of Epic 21.
> See **[Agent Skills](features/skills.md)** for the full documentation.
>
> - `prompt`-type skills replace old prompt slash commands
> - `agent`-type skills replace old agent slash commands
> - Skills are stored in `.taskforce/skills/` instead of `.taskforce/commands/`

## Quick Migration Guide

| Old (slash commands) | New (skills) |
|---|---|
| `.taskforce/commands/review.md` | `.taskforce/skills/review/SKILL.md` with `type: prompt` |
| `.taskforce/commands/agents/architect.md` | `.taskforce/skills/agents/architect/SKILL.md` with `type: agent` |
| `type: prompt` in frontmatter | `type: prompt` in SKILL.md frontmatter |
| `type: agent` in frontmatter | `type: agent` in SKILL.md frontmatter |
| `taskforce commands list` | `taskforce skills list` |
| `taskforce run command <name>` | `taskforce run skill <name>` |

For full documentation see [features/skills.md](features/skills.md).
