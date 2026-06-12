---
name: spec-creator-taskforce
description: |
  Pytaskforce-specific overlay of the generic `spec-creator` skill. Drafts a new `docs/spec/<feature>.md` using pytaskforce conventions: FastAPI routes under `/api/v1`, pytest `@pytest.mark.spec(...)` markers, profile YAML at `src/taskforce/configs/default.yaml`, `EventType` enum in `core/domain/enums.py`, override hooks in `application/infrastructure_overrides.py`, agent-packages-out-of-scope rule, owner `rudi77`, GitHub Project #3. Re-uses `.claude/skills/spec-check/scripts/check_routes.py` and `check_enums.py` for deterministic extraction.

  Trigger this skill (instead of the generic user-level `spec-creator`) when working inside the pytaskforce repo and the user wants a new `docs/spec/<feature>.md`: "spec für gateway erzeugen", "/spec-creator-taskforce settings-store", "draft a spec for the new XYZ feature", "spec doc anlegen für …", "neuen spec anlegen". For projects other than pytaskforce, the generic `spec-creator` skill applies the same drafting logic without these hardcoded assumptions.
---

# spec-creator-taskforce

> Pytaskforce-specific overlay. The generic, project-agnostic version of
> this skill lives at the user level (`~/.claude/skills/spec-creator/`)
> and applies the same drafting logic without the hardcoded paths,
> FastAPI/pytest assumptions, and the "agent-packages out of scope" rule.
> Use the generic skill outside this repo.

Drafts a new `docs/spec/<feature>.md` from the live codebase. One file per
spec point (feature), in the exact shape of `docs/spec/_template.md` and
matching the tone of the existing specs (`cowork.md`, `react-loop.md`,
`gateway.md` are the references — read at least one before drafting).

The mirror of `spec-check`: `spec-check` verifies written claims against
code; `spec-creator` derives claims from code into written form. Both
treat the spec as a **user-facing contract**, not a code map.

## When this triggers

- After shipping a new subsystem that has no spec yet (look at
  `docs/spec/index.md` — rows with `_TODO_` are the obvious candidates)
- When a refactor splits one subsystem into two and a second spec is needed
- When the user wants a draft they can edit, not a fully-baked spec — this
  skill produces ~80% and stops; the user owns the final polish

## Conventions (do not break)

These come from prior memories and from the spec authoring guide
(`docs/spec/README.md`):

- **Behavior first, mechanism never.** "Two projects cannot point at the
  same directory; conflicts return 409" — not "`FileProjectStore.create()`
  raises `ValueError`". Refactors must not break the spec.
- **One file per spec point.** A spec point = a subsystem / feature. One
  feature → one file under `docs/spec/<slug>.md`. Never split a feature
  into per-class files.
- **Lowercase kebab-case filenames.** `react-loop.md`, `channel-ask.md`,
  `settings-store.md`. No prefix for framework features; `agent-` prefix
  is reserved (and currently unused — agent packages are out of spec scope).
- **Agent packages (Butler, Coding, RAG, Security, SWE-Bench) are out
  of scope.** Memory `feedback_agents_out_of_spec`. Refuse the request
  with a one-liner if the user names one — they're tested via evals, not
  specced.
- **Tone-match the existing specs.** Capabilities are written from the
  user/operator POV, invariants state properties (not mechanisms),
  API-surface lines must be parseable as `<METHOD> <path> → <status>
  [on <condition>]`.
- **The framework default profile lives at `src/taskforce/configs/default.yaml`.**
  Agent-package profiles live at `agents/*/configs/`. The skill must glob
  both when looking up config keys.
- **Spec length target: 50–120 lines.** If you're over 150, you're
  enumerating implementation details — pull back.
- **Don't auto-add board issues.** Drafting a spec is not the same as
  filing one. Output is the file + a one-line index entry; no `gh` calls.
- **Don't `unset GITHUB_TOKEN` here** — no `gh` is used. (Mentioned because
  `spec-check` does, and the symmetry is misleading.)

## Phase 0 — Arguments + intake

Parse the user's arguments:

| Flag / arg | Behavior |
|---|---|
| `<feature-slug>` (positional, required) | The kebab-case slug for the new spec, e.g. `settings-store`. Becomes the filename and the `feature:` frontmatter key. |
| `--name "<display name>"` | The H1 + section title (e.g. `"Settings Store — Encrypted Runtime Config"`). If omitted, derived from the slug. |
| `--status <value>` | One of `shipped`, `partial`, `wip`, `legacy`, `deprecated`, `enterprise`. Default `wip` (safest — promotes after first verification). |
| `--paths <comma-separated>` | Hint at the code paths that implement this feature (e.g. `src/taskforce/application/gateway.py,src/taskforce/api/routes/gateway.py`). Optional — skill will Grep for the slug if omitted. |
| `--adr <ADR-NNN>` | Architecture decision reference if one exists. Optional. |
| `--owner <gh-handle>` | Owner. Default `rudi77` (matches existing specs). |
| `--overwrite` | Overwrite an existing `docs/spec/<slug>.md`. Default is to refuse with a clear error so accidental clobbers don't happen. |

If `<feature-slug>` is missing, ask the user (this is the one input the
skill cannot infer). Everything else has a sensible default.

If the slug refers to an agent package (e.g. `butler`, `coding-agent`),
refuse with: "Agent packages are out of spec scope — they're tested via
evals, not specs. See `docs/spec/index.md` → 'Agent Packages — NOT in
spec scope'." Do not draft.

If `docs/spec/<slug>.md` already exists and `--overwrite` was not
passed, refuse with: "Spec already exists. Pass `--overwrite` to
replace, or pick a different slug." Do not draft.

## Phase 1 — Gather raw signals from the code (parallel)

Run these in parallel — they're cheap, deterministic, and feed the
drafting phase.

### 1a — Read the template and at least one reference spec

```
Read docs/spec/_template.md
Read docs/spec/cowork.md           # CRUD/REST feature reference
Read docs/spec/react-loop.md       # engine/event-stream feature reference
```

Keep the tone of these in mind while drafting. Phrasing matters more than
structure — the structure is enforced by the template.

### 1b — Extract registered routes (for the API surface section)

Reuse the spec-check route extractor (already exists, stdlib-only):

```bash
python .claude/skills/spec-check/scripts/check_routes.py src/taskforce/api/routes/ > /tmp/spec_creator_routes.json
```

This emits every `(METHOD, path, status_code, response_codes, file, line)`
tuple registered under `/api/v1`. Filter the output to routes whose
`path` or `file` matches the feature slug (or the user's `--paths` hint)
— those are the candidates for the API surface section.

If no routes match, the feature is engine-only — skip the API surface
section entirely. Don't fabricate routes.

### 1c — Extract event-type enum members (for the event stream section)

Reuse the spec-check enum extractor:

```bash
python .claude/skills/spec-check/scripts/check_enums.py src/taskforce/core/domain/enums.py > /tmp/spec_creator_enums.json
```

This emits all members of `EventType`, `LLMStreamEventType`, etc. If the
feature emits stream events (typical for engines like ReAct, content
filter recovery, interruption), identify which enum members are emitted
by Grep-ing the feature's code:

```
Grep -n "EventType\.<NAME>" in <feature-paths>
Grep -n "LLMStreamEventType\.<NAME>" in <feature-paths>
```

Document only the events that are part of the **public contract** for
callers (UI, SSE, CLI) — internal-only events stay out.

### 1d — Read the framework default profile (for configuration surface)

```
Read src/taskforce/configs/default.yaml
Glob agents/*/configs/*.yaml          # for agent-package profile keys
Read src/taskforce/core/domain/config_schema.py
Read src/taskforce/application/config_schema.py
```

The default YAML lists what an operator can configure; the schema
modules document type + default. For each top-level YAML section the
feature owns (`agent.*`, `memory.*`, `gateway.*`, ...), list the keys
the feature consumes and their defaults.

### 1e — Find extension points (override hooks + entry-point groups)

```
Read src/taskforce/application/infrastructure_overrides.py
Grep -n "set_.*_override\b" in src/taskforce/application/infrastructure_overrides.py
Grep -rn 'entry_points = ' in pyproject.toml agents/*/pyproject.toml cli/pyproject.toml
```

For each override hook whose name relates to the feature, document the
hook with: name, module path, what it overrides, when it's resolved
(per-request vs cached). Same for entry-point groups
(`taskforce.tools`, `taskforce.cli_apps`, `taskforce.config_dirs`).

If the feature has no documented seams, skip the section.

### 1f — Find existing tests + spec markers

```
Grep -rn '@pytest.mark.spec\(' tests/                      # existing markers
Grep -rln '<feature-slug>' tests/                          # tests that touch the feature
```

Two purposes:
1. If `@pytest.mark.spec("<slug>.…")` markers already exist, list them
   verbatim in the Tests section.
2. If only unmarked tests exist, propose target marker names derived
   from the assertion (e.g. `spec("settings-store.write_encrypts_at_rest")`)
   — add them to Tests and add a Known-gap note: "no tests carry the
   marker yet; section asserts the target, not current state."

### 1g — Read related docs (for cross-references)

```
Glob docs/features/<slug>.md         # user guide if any
Glob docs/adr/adr-*-<slug>*.md       # related ADRs
Glob docs/adr/adr-*<relevant-keyword>*.md
```

These become the `## Cross-references` section. Navigational only —
don't verify, don't promise the links resolve.

### 1h — Read the feature code itself (for capabilities + invariants)

This is the most important read. Use the user's `--paths` hint, or if
absent, Grep for the slug and follow the obvious entry points:

```
Read each file in --paths (or discovered paths) end-to-end
Read the related interface files (core/interfaces/<feature>.py if it exists)
```

The capabilities and invariants are the only sections the skill cannot
mechanically derive — they require judgement. The code reading here
informs the drafting in Phase 2.

## Phase 2 — Draft the spec sections

Compose the file in the order of `_template.md`. Use the gathered
signals; **drop sections that don't apply**. Below are per-section
drafting rules.

### Frontmatter

```yaml
---
feature: <slug>
status: <from --status, default wip>
since: <git log -1 --format=%ad --date=short -- <one of the feature paths>>
last_verified: <today's date>
owner: <from --owner, default rudi77>
adr: <from --adr, omit field if not provided>
---
```

Derive `since:` from `git log -1 --format=%ad --date=short -- <path>`
using the earliest of the feature's main files. If the path doesn't
exist yet (drafting alongside new code), use today's date.

### H1 + overview paragraph

```markdown
# <Display Name> — <Subtitle>

<One paragraph, 4-6 lines, plain language, user/operator POV. What does
this feature do for the user? What's the minimum a reader needs to make
sense of the rest of the spec?>
```

Keep it under 6 lines. If longer, the detail belongs in `docs/features/`.

### Capabilities

Derived from: public-facing API routes, CLI subcommands, profile YAML
keys, and the agent/operator-visible side effects in the code. Phrase
from the user's POV. One line per capability.

✅ "create a project from scratch OR by importing an existing directory"
❌ "The `ProjectStoreProtocol.create()` method accepts a name and path"

If the feature has 0 user-visible capabilities (purely internal), the
spec probably shouldn't exist — flag this back to the user instead of
inventing capabilities.

### Invariants

Derived from: behavioral guarantees the code enforces — concurrency
guards, atomic writes, fail-closed checks, "never deletes user files",
"always emits exactly one terminal event", etc. State the property, not
the mechanism. Make each one independently testable.

If you cannot name a concrete property that must always hold, leave the
invariant out. Vague invariants ("must work correctly") are an
anti-pattern.

Target: 3–10 invariants for a non-trivial feature.

### API surface

Use the routes extracted in Phase 1b. Format each line as:

```
<METHOD> <path> → <status> [on <condition>]
```

Examples:
```
- POST /api/v1/projects → 201 created
- POST /api/v1/projects → 409 on duplicate path
- GET  /api/v1/projects/{project_id} → 404 if missing
```

For routes the feature extends rather than owns:
```
- POST /api/v1/conversations accepts optional `project_id` in body
- GET  /api/v1/conversations accepts `project_id` as query filter
```

Skip this section if the feature has no REST surface.

### Configuration surface

Use the YAML keys from Phase 1d. Format:

```
- `agent.example_key: <type>` (default `<value>`) — what it does
- `ENV_VAR_NAME` — purpose, allowed values
```

Skip if the feature has no operator-facing configuration.

### Event stream contract

Use the enum members + grep hits from Phase 1c. Format:

```
- `EVENT_NAME` — when it fires, what's in the payload
```

Only list events callers of the public stream must handle. Skip if the
feature emits no stream events.

### Extension points

Use the override hooks + entry-point groups from Phase 1e. Format:

```
- `set_<thing>_override` (`application/infrastructure_overrides.py`) — what
  it replaces and when it's resolved
- `<entry_point_group>` entry-point group — what plugins register here
```

Skip if the feature has no documented seams.

### Tests

Use markers + test paths from Phase 1f. Format:

```
- spec("<feature-slug>.<assertion_in_snake_case>")
```

Convention: `<slug>.<short_assertion>`. If no markers exist yet, list
the **target** markers (one per important invariant + key capability)
and add a Known-gap entry making the absence visible.

### Known gaps

State exactly what's broken or missing. Be specific. Optional tracking
metadata:

```markdown
- Foo is missing
  - tracked_in: issue #NNN
  - eta: 2026-MM
```

Always include "(none)" if truly empty — the section is mandatory by
convention.

If no spec markers exist yet, always add a Known-gap entry like:
"No backend `@pytest.mark.spec` markers exist yet — the Tests section
above asserts the target, not current state."

### Cross-references

Navigational only. Use docs/ADRs/related-spec links from Phase 1g:

```
- related_spec: <other-feature>.md
- adr: ADR-NNN
- docs: docs/features/<slug>.md (user guide)
- commit: <hash> (first introduced, optional)
```

## Phase 3 — Write the file + index entry

Write the assembled spec to `docs/spec/<slug>.md`. Refuse to overwrite
unless `--overwrite` was passed.

Then propose (don't auto-apply) an `index.md` row. Show it to the user
so they can paste it into the right category. Example for a CRUD feature:

```markdown
| NN | <Display Name> | <status> | [<slug>.md](<slug>.md) | <one-line description> |
```

Pick the right category by domain (`Core Framework`, `LLM & Routing`,
`Memory & Persistence`, `Communication & Events`, `Security & Auth`,
`Workflows & Runtime`, `Cross-Agent Protocols`, `Observability`,
`Enterprise / Multi-Tenant`, `API, CLI, UI`). If unsure, recommend a
category but ask the user before editing `index.md`.

Do **not** edit `index.md` automatically — the index is a curated table,
not a generated artifact. The user owns ordering.

## Phase 4 — Self-review the draft

Before reporting "done", check the draft against the writing rules in
`docs/spec/README.md`:

- [ ] No file/class/method names in capabilities or invariants (those
      should survive refactors)
- [ ] No "needs work" or "TODO" entries in Known gaps — be specific
- [ ] Every API-surface line matches the format
      `<METHOD> <path> → <status> [on <condition>]`
- [ ] Total length ≤ 120 lines (warn if higher)
- [ ] At least 3 invariants for a non-trivial feature (warn if fewer)
- [ ] At least one Test marker target (warn if none — the spec asserts
      coverage)
- [ ] `last_verified:` equals today's date
- [ ] No leaked jargon from `core/domain/`, `infrastructure/`, etc. in
      capabilities (user POV only)

If any check warns, flag it in the final output so the user knows what
to polish.

## Phase 5 — Final output to the user

End with a short summary:

```
## Spec entworfen: docs/spec/<slug>.md

**<Display Name>** (status: <status>)
- <N> capabilities
- <N> invariants
- <N> API routes
- <N> config keys
- <N> event types
- <N> extension points
- <N> test markers (<M> already present, <K> new targets)

**Selbst-review:**
- [ ] check 1
- [x] check 2 — flagged: <reason>
...

**Vorgeschlagene index.md-Zeile (Kategorie: <category>):**
| NN | <name> | <status> | [<slug>.md](<slug>.md) | <description> |

Datei liegt bei docs/spec/<slug>.md — bitte review + ggf. polieren,
dann in index.md eintragen.
```

Do not commit. The user reviews the draft and edits as needed.

## Anti-patterns (don't do these)

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Enumerating files, classes, fields in capabilities/invariants | Spec breaks on every refactor | State behaviour, not mechanism |
| Drafting a spec for an agent package | Out of scope per index.md | Refuse and point at evals |
| Auto-editing `index.md` | Wrong category, wrong ordering | Propose the row, let the user paste |
| Auto-committing the draft | User loses the review pass | Output only — user commits |
| Inventing routes/events/keys not in code | Spec lies | Only emit what Phase 1 found |
| Skipping the reference-spec read | Tone drifts, format inconsistent | Always read at least cowork.md or react-loop.md |
| Writing vague invariants ("must work correctly") | Untestable, useless | If you can't name a concrete property, drop it |
| Overwriting without `--overwrite` | Silent destruction | Refuse by default |
| Adding `gh` calls | Drafting ≠ filing issues | No `gh` calls — that's `spec-check --create-issues` territory |
| Drafting >120 lines | Implementation catalogue, not contract | Cut to ≤ 120; pull detail to `docs/features/` |
| Using English-only descriptions when the surrounding doc is German | Mismatched voice | Match the codebase convention — the existing specs are English; keep that |
