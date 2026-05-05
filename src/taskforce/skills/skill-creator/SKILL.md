---
name: skill-creator
description: Author a new Taskforce skill (context, prompt, or agent type). Activate when the user asks to create, build, scaffold, or implement a skill (e.g. "implementiere einen Skill", "create a skill", "neuer Workflow als Skill").
type: context
---

# Skill Creator

You are now in **skill-creator mode**. Help the user produce a valid Taskforce skill in **one delegation wave** — no exploratory back-and-forth. Stop as soon as the file is written and verified.

## What a Taskforce skill is

A skill is a directory containing a single `SKILL.md` with YAML frontmatter and a Markdown body, optionally accompanied by `scripts/`, `references/`, or `assets/`. The parser is `taskforce.infrastructure.skills.skill_parser.parse_skill_markdown`.

**Discovery roots (in load order):**
- `.taskforce/skills/<name>/SKILL.md` — project-level (current project; **default target for new skills**)
- `~/.taskforce/skills/<name>/SKILL.md` — user-level (shared across projects)
- `src/taskforce/skills/<name>/SKILL.md` — bundled with the framework distribution (only edit when working inside `pytaskforce` itself)

When unsure where to write the skill, default to the project-level path `.taskforce/skills/<slug>/SKILL.md`.

## Required frontmatter

```yaml
---
name: <slug>            # required, kebab-case; LAST segment must equal directory name
description: <one line> # required; explain what AND when to activate
type: context           # optional: context (default) | prompt | agent
---
```

Hierarchical names use `:` and a matching directory layout, e.g. `name: agents:reviewer` lives in `agents/reviewer/SKILL.md`.

### Type-specific fields

| Type      | Invocation                       | Extra frontmatter                                |
|-----------|----------------------------------|--------------------------------------------------|
| `context` | `activate_skill` or intent route | none required                                    |
| `prompt`  | `/name [args]` in chat           | body should reference `$ARGUMENTS`               |
| `agent`   | `/name [args]` in chat           | `profile`, `tools` (list), `mcp_servers`, `specialist` |

Optional fields: `slash-name` (overrides the slash trigger), `allowed-tools` (space-delimited), `metadata` (string→string map), `compatibility`, `license`, `workflow` (deterministic step engine — only when explicitly requested).

## Authoring workflow

1. **Decide the type** (`context`/`prompt`/`agent`). For Butler/automation-style skills, default to `context`.
2. **Pick a slug** — kebab-case, no umlauts (use `ae`/`oe`/`ue`/`ss`), no `--`, must not start/end with `-`, ≤ 64 chars.
3. **Decide the location**: default to `.taskforce/skills/<slug>/SKILL.md`. Only use `src/taskforce/skills/` when the user is editing the framework repo itself.
4. **Write the file in ONE `file_write` call.** Do NOT write a partial file and amend it.
5. **Validate** with the helper script:
   ```
   python src/taskforce/skills/skill-creator/scripts/validate_skill.py <path-to-SKILL.md>
   ```
   The script reuses `taskforce.infrastructure.skills.skill_parser` so the validation matches what the runtime will accept.
6. **Verify discovery** with `taskforce skills list` (or `taskforce skills show <name>`). For prompt/agent skills, also note the slash form (`/<slug>` or `/<slash-name>`).
7. **Stop and report**: tell the user the absolute path, the type, and the activation form. Do NOT keep iterating once validation passes.

## Templates

### Context skill (default)

```markdown
---
name: <slug>
description: <what it does and when to activate>
type: context
---

# <Title>

## When to activate
<Concrete trigger phrases or intents.>

## Workflow
1. <step>
2. <step>

## Tools
- <tool short name> — <why>

## Output
<Expected user-facing output format.>
```

### Prompt skill

```markdown
---
name: <slug>
description: <what it does>
type: prompt
---

<Instructional template>

$ARGUMENTS
```

### Agent skill

```markdown
---
name: agents:<slug>
description: <specialised behaviour>
type: agent
profile: coding_agent
tools:
  - file_read
  - file_write
  - shell
---

You are a <role>. <Behavioural rules>

$ARGUMENTS
```

## Hard rules

- **One write, one validation, then stop.** Never re-delegate to the same sub-agent for the same skill.
- **Never invent tool short names.** Pick from the registry (`taskforce tools list`). Examples of registered names: `file_read`, `file_write`, `edit`, `grep`, `glob`, `python`, `shell`, `powershell`, `web_search`, `web_fetch`, `wiki`, `ask_user`, `activate_skill`. There is **no** `search` tool — use `grep`/`glob` or `powershell`.
- **Skill name's last segment must match the directory name.** `name: agents:reviewer` → directory `agents/reviewer/`.
- **Description must convey both *what* and *when*.** This is what the intent router uses for context skills.
- **Do not generate documentation files (README, CHANGELOG) unless the user explicitly asks** — `SKILL.md` alone is the contract.

## Failure handling

- If `file_write` fails (path missing, permission denied) → create the parent directory in **one** `shell`/`powershell` call and retry once.
- If validation reports a parser error → fix the specific field the error names, do **not** rewrite the whole file from scratch.
- If validation still fails after one fix → stop and report the error to the user verbatim.
