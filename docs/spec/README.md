# Taskforce Spec — Authoring Guide

This directory holds **system contracts** written from the user's perspective.
For each feature, a markdown file states what the user can do, what must
always be true, and what the API surface looks like. The `spec-check` skill
verifies each claim against the live codebase and reports drift, regressions,
and silent deletions.

This guide is for **humans writing or maintaining specs**. The spec is your
product contract, not a code map.

---

## Core principle: behavior first, mechanism never

A spec describes **what the feature does for the user**, not how it's
implemented. Refactors that rename a class or move a file should leave the
spec untouched. Real regressions — a missing route, a broken invariant, a
removed capability — should make the spec fail.

So:

- ✅ "Two projects cannot point at the same directory; conflicts return 409"
- ❌ "Class `FileProjectStore` has a method `create` that raises `ValueError`"

The first survives any refactor and still catches the real bug. The second
breaks every time you touch the code, useful or not.

---

## What a spec is — and is not

| A spec **is** | A spec **is not** |
|---|---|
| The user-/client-facing contract | A code map |
| Updated in the same PR as a feature change | A design doc or rationale (that's an ADR) |
| One file per subsystem | One file per class or function |
| Behavior + API + invariants | A re-statement of the source code |
| Short — usually 50-100 lines | A 300-line catalogue of internals |

---

## File anatomy

Every spec uses the same skeleton (see `_template.md`):

```markdown
---
feature: <slug>
status: <shipped|partial|wip|legacy|deprecated|enterprise>
since: 2026-MM-DD
last_verified: 2026-MM-DD
owner: <github-handle>
adr: ADR-NNN              # optional
---

# Feature Name

One-paragraph overview.

## Capabilities                  # always
## Invariants                    # always
## API surface                   # for REST-exposed features
## Configuration surface         # for config-driven features (engines, daemons)
## Event stream contract         # for features that emit StreamEvents
## Extension points              # for features with documented seams
## Tests                         # always
## Known gaps                    # always (use "(none)" if truly empty)
## Cross-references              # always
```

Drop sections that don't apply. Most features use a subset:

- A REST-driven CRUD feature (e.g. CoWork): `API surface`, no `Configuration` / `Event stream`
- A config-driven engine (e.g. ReAct loop): `Configuration surface` + `Event stream contract`, no `API surface`
- A protocol-only contract (e.g. Skills system): `Configuration` + `Extension points`, no `API surface`

---

## How the skill verifies each section

| Section | How it's checked | Cost |
|---|---|---|
| Capabilities | LLM sub-agent reads the relevant code and confirms each capability is achievable through the documented API | medium |
| Invariants | LLM sub-agent reads the implementation files (it finds them itself) and answers PASS / FAIL / UNCERTAIN per invariant | medium-high |
| API surface | Parser walks FastAPI decorators; for each documented endpoint, confirms it's registered and (where stated) returns the documented status codes | cheap |
| Configuration surface | Parser checks profile YAML / env var defaults match what the spec claims | cheap |
| Event stream contract | Parser checks every documented event name is a member of the relevant Enum (e.g. `EventType` in `core/domain/enums.py`); LLM verifies the documented payload is what callers actually receive | cheap + LLM |
| Extension points | Grep for the named symbol in the package(s) that should expose it | cheap |
| Tests | `pytest -m 'spec("...")' --collect-only` per marker; then runs if collected | cheap |
| Known gaps | Reported as info, not failure — the user has acknowledged them | free |
| Cross-references | Not verified; navigational only | free |

The pattern: **deterministic checks first** (API surface, extension points,
tests). If those pass, **LLM checks next** (capabilities, invariants). If
the LLM says FAIL, **spot-check is mandatory** before filing a regression
issue — the verifier should never create false-positive issues.

---

## Writing capabilities

Phrase from the user's POV. Drop jargon. Keep each bullet to one line.

✅ Good:
```markdown
- create a project from scratch OR by importing an existing directory
- list all projects, newest first
- remove a project without losing the on-disk files
```

❌ Avoid:
```markdown
- The `ProjectStoreProtocol.create()` method accepts a name and path string
- The `list()` method returns `list[Project]` sorted by `created_at` desc
- `delete()` is a side-effect-free registry operation
```

The first set survives any refactor. The second breaks if `Project` is renamed.

---

## Writing invariants

State the property, not the mechanism. Make each one independently testable —
imagine a tester reading just that one line and writing a test.

✅ Good:
```markdown
- Removing a project never deletes the user's on-disk files
- Concurrent attempts to create the same project cannot both succeed
- Conversations without a project_id remain fully usable
```

❌ Avoid:
```markdown
- The `delete()` method does not call `shutil.rmtree`
- A module-level `asyncio.Lock` keyed by file path serialises `create()`
- The `project_id` field in `Conversation` is `Optional[str]`
```

If you find yourself naming variables or describing locks, you're describing
how, not what. Rephrase.

---

## Writing API surface entries

Each entry should be parseable by a simple regex. Format:

```
<METHOD> <path> → <status> [on <condition>]
```

Examples:
```markdown
- POST /api/v1/projects → 201 created
- POST /api/v1/projects → 409 on duplicate path
- GET  /api/v1/projects/{id} → 404 if missing
- DELETE /api/v1/projects/{id} → 204
```

For routes the feature extends rather than owns:

```markdown
- POST /api/v1/conversations accepts optional `project_id` in body
- GET  /api/v1/conversations accepts `project_id` query filter
```

Don't enumerate every possible 4xx. Document the ones a client must handle.

---

## Writing extension points

Only list seams that other packages (plugins, enterprise overlay,
host-app integrations) are documented to use. Skip private helpers.

```markdown
- `set_project_store_override` — enterprise plugins use this to tenant-scope
  projects. Resolved per-request, not cached.
- `taskforce.tools` entry-point group — plugins register tools by short name.
```

Skip the section entirely if the feature has no documented extension points.

---

## Writing tests

Each line is a `pytest` marker string. Names should describe the assertion,
not the test function.

```markdown
- spec("cowork.create_duplicate_path_returns_409")
- spec("cowork.delete_keeps_directory")
- spec("cowork.conversation_without_project_id_uses_global_workdir")
```

Convention: `<feature-slug>.<assertion_in_snake_case>`. Keep them short
enough to fit on the screen without wrapping.

The test code itself uses the matching decorator:

```python
@pytest.mark.spec("cowork.delete_keeps_directory")
async def test_delete_project_does_not_remove_directory(tmp_path): ...
```

Listing a marker for a test that doesn't exist is fine — the skill reports
"asserted but no test" as a P1 finding so the gap is visible. That's better
than silently passing because there's no test to fail.

---

## Writing known gaps

State exactly what's broken or missing. The skill reports these as info,
so the user sees "yes, you knew about this" rather than panicking at red.

✅ Good:
```markdown
- Project deletion does not cascade to conversations. A conversation
  pointing at a deleted project will fail to resolve its working_dir
  on next execution.
- No backend tests have `@pytest.mark.spec` markers yet — Tests section
  asserts the target, not current state.
```

❌ Avoid:
```markdown
- Needs more tests
- Some edge cases unhandled
- TODO
```

Vague gaps are useless — they don't help future-you decide if the gap still
applies. If you don't know enough to be specific, leave the gap out and add
it when you do.

Optional metadata per gap:
```markdown
- Foo is missing
  - tracked_in: issue #NNN
  - eta: 2026-MM
```

---

## Severity mapping (when spec-check finds drift)

| Finding type | Severity | Why |
|---|---|---|
| Documented API route not registered | **P0** | API contract broken |
| API route returns wrong status code | **P1** | client may handle wrong |
| Invariant LLM-check returns FAIL | **P0** or **P1** | judged by impact (data loss = P0, UX = P1) |
| Invariant LLM-check returns UNCERTAIN | **P2** | spec is ambiguous, rewrite |
| Capability not achievable via API | **P0** | feature gone or broken |
| Extension point symbol not found | **P1** | plugin contract broken |
| `spec(...)` test missing | **P1** | spec asserts coverage but no test |
| `spec(...)` test fails | **P0** | direct regression |
| Code introduces a feature not in any spec | **P2** | spec gap — new feature undocumented |
| Known gap from `## Known gaps` | **info** | acknowledged |

---

## Status field semantics

| Value | Meaning |
|---|---|
| `shipped` | Production-ready. Spec is the contract. Drift fails CI. |
| `partial` | Code exists, not feature-complete. Spec lists what's missing under Known gaps. |
| `wip` | Active development in last 2 weeks. Findings are warnings, not CI-fail. |
| `legacy` | Older feature, may be replaced. Treated like `shipped` until removed. |
| `deprecated` | Explicitly retired. Spec stays until the code is gone, then deleted. |
| `enterprise` | Only available with `taskforce-enterprise` plugin installed. Spec-check skips unless plugin detected. |

---

## Update process

When you change code that affects a feature's contract:

1. **In the same PR**, edit `docs/spec/<feature>.md` to reflect the new contract
2. Adding a capability → add a bullet
3. Removing one → delete the bullet (and the code in the same PR)
4. Bump `last_verified:` to the merge date
5. If the change is breaking, also bump `since:` or move to a new feature spec

CI will (eventually) enforce: any PR touching `src/taskforce/api/routes/` or
core agent code without touching a spec gets a comment asking why.

---

## Writing a new spec — checklist

1. Copy `_template.md` to `<feature>.md`
2. Fill the frontmatter (slug, status, since, owner)
3. Write the 1-paragraph overview from the user's POV
4. Walk through each section, deleting the ones that don't apply
5. **Read the actual code** — every claim must reflect what's true today, not
   what you remember or what the PRD said
6. Add the row to `index.md` (or remove the `_TODO_` marker)
7. (Later, once the skill exists:) run spec-check against the draft, correct
   spec or code based on what fails

A good spec for a medium feature is 50-90 lines. If you're over 150, you're
probably enumerating implementation details — pull back.

---

## Anti-patterns (don't do these)

- **Enumerating files, classes, or fields.** That's `git ls-files`, not a spec.
- **Restating test bodies.** A spec marker is enough.
- **Vague invariants** like "must work correctly". Be testable.
- **Specs for things you might build** — that's a PRD or epic, not a spec.
- **Cross-spec duplication.** If two specs talk about the same route, one owns
  it and the other says `related_spec:`.
- **Implementation jargon in capabilities.** Phrase from the user's POV.
- **Hidden TODOs.** Either write the spec or don't list the feature in
  `index.md`. `_TODO_` rows are visible; vague half-specs aren't.
