---
name: workflow-builder
description: Guides the agent through interactively designing and creating multi-agent workflow skills. Activate when the user wants to create, design, or build a new workflow or automation pipeline.
type: context
---

# Workflow Builder

You are now in **workflow builder mode**. Help the user design a reusable multi-agent workflow and persist it as a Taskforce skill.

## What Is a Workflow Skill?

A workflow skill is a SKILL.md file that describes a multi-step process. When activated, its instructions are injected into the agent's system prompt, guiding it to orchestrate sub-agents and tools in a defined sequence.

Workflow skills live in `.taskforce/skills/<name>/SKILL.md` and can be invoked via:
- `activate_skill` tool (programmatically)
- `/name` in chat (for prompt or agent type skills)
- Intent routing (for context type skills)

## Design Process

Follow these steps to help the user create a workflow:

### Step 1: Understand the Goal

Ask the user:
- What should the workflow accomplish?
- What inputs does it need? (files, URLs, text, etc.)
- What outputs should it produce? (reports, files, notifications, etc.)
- Should it run interactively or fully automated?

### Step 2: Identify the Steps

Break the workflow into sequential steps. For each step determine:
- **What** needs to happen (action description)
- **Who** does it (which sub-agent specialist or tool)
- **Inputs** for this step (from user input or previous step outputs)
- **Outputs** this step produces (for subsequent steps or final result)

Available sub-agent specialists (via `parallel_agent` / `call_agent`):
- `pc-agent` — Local files, folders, system info, processes
- `web-agent` — Web search, URL fetching, scraping
- `research_agent` — Multi-step research, data collection, reports
- `coding_agent` — Code writing, scripts, debugging, automation
- `analysis_agent` — Data analysis, calculations, reports

Available direct tools (no sub-agent needed):
- `file_read`, `file_write`, `shell`, `python` — Local operations
- `web_search`, `web_fetch` — Web access
- `memory` — Long-term memory read/write
- `send_notification` — Push notifications
- `calendar`, `gmail` — Google integrations
- `ask_user` — Interactive user input

### Step 3: Choose the Skill Type

| Type | Use When |
|------|----------|
| `context` | Workflow should guide the current agent's behavior. Best for Butler workflows. |
| `prompt` | One-shot execution with `$ARGUMENTS` substitution. Best for simple pipelines. |
| `agent` | Full agent config override with specific profile/tools. Best for specialized agents. |

For Butler workflows, prefer `context` type — the Butler activates the skill, gets the instructions injected, and follows them using its existing sub-agent delegation capabilities.

### Step 4: Write the SKILL.md

Use `file_write` to create the skill file. Follow this template:

```markdown
---
name: <skill-name>
description: <one-line description of what the workflow does>
type: context
---

# <Workflow Title>

## Objective
<What this workflow accomplishes>

## Required Input
- <input 1>: <description>
- <input 2>: <description>

## Workflow Steps

### Step 1: <Step Name>
- **Action**: <what to do>
- **Agent/Tool**: <which specialist or tool>
- **Input**: <what this step needs>
- **Output**: <what this step produces>

### Step 2: <Step Name>
...

## Output Format
<How the final result should be structured>

## Error Handling
- If step X fails: <fallback action>
- If input is missing: <ask user via ask_user tool>
```

### Step 5: Activate and Test

After writing the SKILL.md:

1. Call `activate_skill(skill_name="<name>")` — the registry auto-refreshes to discover the new file
2. The skill instructions are now in your system prompt
3. Follow the workflow steps using the appropriate sub-agents and tools
4. Report results to the user

## Best Practices

- **Keep steps atomic** — each step should do one thing well
- **Use sub-agents for complex work** — delegate research, coding, analysis to specialists
- **Handle failures gracefully** — include fallback actions for each step
- **Produce structured output** — use consistent formats (Markdown, JSON) between steps
- **Save intermediate results** — use `file_write` to persist step outputs for debugging
- **Notify on completion** — use `send_notification` for long-running workflows
