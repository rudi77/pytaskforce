# Long-Term Memory (Wiki-Style)

> **Status:** Current (supersedes the record-based memory from ADR-007/013/014).
> See [ADR-020](../adr/adr-020-wiki-style-memory.md) for the decision record.

## TL;DR

Long-term memory is a **personal wiki** of markdown pages that the agent
curates itself. One page per topic, grouped under `entities/`,
`preferences/` and `concepts/`. The agent searches the wiki at the
start of a new topic, writes a page the first time a reusable fact
appears, and updates the existing page on every subsequent mention of
the same thing. No deduplication pipeline, no consolidation, no decay.

## Directory layout

```
.taskforce/
└── memory/
    ├── memory.md.archive-YYYY-MM-DD   # optional — the old record store, kept read-only
    └── wiki/
        ├── index.md                    # one-line summary per page, grouped by kind
        ├── log.md                      # append-only event log
        ├── entities/                   # people, companies, accounts, contacts
        ├── preferences/                # formats, workflows, personal choices
        └── concepts/                   # process rules, patterns
```

## Page format

Each page is a small YAML frontmatter block plus a markdown body. The
body contains `##` sections that group related facts, making targeted
updates safe. A `## Related` section with `[[kind/slug]]` cross-links
is conventional.

```markdown
---
title: Steuerberater Mueller
tags: [kontakt, steuer]
created_at: 2026-04-21T22:15:00+00:00
updated_at: 2026-04-21T22:15:00+00:00
---

# Steuerberater Mueller

## Kontakt
- Tel: 0664-1234567
- Email: mueller@example.at

## Notizen
- Zuständig für Jahresabschluss 2025.

## Related
- [[preferences/bookkeeping-formats]]
```

## The `wiki` tool

Agents interact with the wiki through a single tool with the following
actions:

| Action | Purpose |
|--------|---------|
| `list_pages` | Load `index.md` |
| `read_page(name)` | Read one page (e.g. `entities/steuerberater-mueller`) |
| `search(query, limit)` | Top-N pages by relevance to `query` |
| `write_page(name, title, content, tags)` | Create or fully overwrite a page |
| `update_page(name, section, content, mode)` | Append/replace one `## section` |
| `delete_page(name)` | Remove a page |
| `log(entry)` | Append a one-line event to `log.md` |

Page names use `<kind>/<slug>` form; slugs are lowercase with hyphens
and no German umlauts (ae/oe/ue/ss).

## Agent workflow

**At the start of a new topic** — agents are instructed in their system
prompt to run `wiki(action=search, query=...)` before asking the user
for anything that might already be in the wiki.

**When the user reveals reusable info** — preferences, recurring
contacts, deadlines, corrections, workflow rules, specific numbers/IDs
— the agent first searches, then updates the matching page in place
(`mode=append` or `mode=replace`) or creates a new one. Every save is
followed by a `log(entry=...)` call so the log stays usable as a
timeline.

**When correcting an existing fact** — use `update_page` with
`mode="replace"` on the targeted section. Do not delete and recreate
the whole page — that loses the created-at timestamp and any unrelated
sections.

## CLI

```bash
taskforce wiki list                        # list all pages
taskforce wiki show entities/mueller       # render one page
taskforce wiki lint                        # orphan/broken-link check
```

## Profile configuration

```yaml
tools:
  - wiki
  # ... other tools

wiki:
  store_dir: .taskforce/memory/wiki        # optional — derived from persistence.work_dir
  context_injection:                        # optional — tune auto-injection
    max_total_chars: 2000
    top_k_relevant: 5
    include_index: true
```

When `wiki` is in the tool list, the framework auto-injects the current
`index.md` (plus up to N relevant page summaries matching the mission)
into the system prompt at session start. This is how the agent knows
what pages exist without having to `list_pages` manually every turn.

## Migration from the old record store

Existing `memory.md` files are left in place but renamed to
`memory.md.archive-YYYY-MM-DD` during upgrade. The new wiki starts
empty. Users who want to carry a handful of curated preferences
forward can copy them into the new pages manually — most of the old
record volume was consolidation noise that is safe to drop.

`ConsolidationService`, `DreamService` and `LearningService` no
longer exist. Their previous role — refining memory in the background
— is now the agent's responsibility at save-time.

## See also

- [ADR-020 — Wiki-Style Long-Term Memory](../adr/adr-020-wiki-style-memory.md)
- `agents/butler/configs/butler.agent.md` — reference system prompt
  that teaches the save/recall workflow.
