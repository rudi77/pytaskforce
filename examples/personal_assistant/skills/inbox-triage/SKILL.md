---
name: inbox-triage
description: Triage inbox emails and propose next actions, drafts, or follow-ups.
---

# Inbox Triage Skill

## Objective
Classify inbox emails and recommend concrete next actions.

## Workflow
1. List inbox emails (status=inbox) and group by sender/subject.
2. Flag urgent emails and summarize required responses.
3. Draft responses only when asked; otherwise propose reply outlines.
4. Suggest task creation for actionable items.

## Output Format
- **Urgent**: Emails requiring same-day response.
- **Follow-ups**: Emails to respond within 3-7 days.
- **Info Only**: Emails to archive or ignore.
