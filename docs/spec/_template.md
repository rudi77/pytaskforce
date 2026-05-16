---
feature: my-feature-slug
status: shipped              # shipped | partial | wip | legacy | deprecated | enterprise
since: 2026-MM-DD            # first-shipped date (from git log)
last_verified: 2026-MM-DD    # update whenever spec-check passes cleanly
owner: github-handle
adr: ADR-NNN                 # optional — link to architecture decision record
---

# Feature Name — Short Display Name

One paragraph of plain-language overview. What problem does this solve for
the user? Who uses it? What's the minimum a reader needs before the rest of
the spec makes sense? Keep it under 6 lines — anything longer belongs in
`docs/features/`.

## Capabilities (what the user can do)

Bullet list, plain English, one capability per line. Phrased from the user's
perspective, not the implementer's. "The user can X" or just "X" — both are
fine. Skip anything that's implementation detail.

- capability one
- capability two
- capability three

## Invariants (what must always be true)

Bullet list, plain English, one invariant per line. State the property, not
the mechanism. The spec-check skill verifies each one by reading the code
that implements the feature.

- Property that must always hold
- Another property
- An edge-case invariant (concurrency, error path, etc.)

## API surface (the contract clients depend on)

REST endpoints (or other public APIs) that callers depend on. Each line is
verified mechanically — the route is parsed out of FastAPI decorators and
the documented status codes are checked. Skip this section for engine /
library features that have no REST surface.

Format: `<METHOD> <path> → <status> [on <condition>]`

- POST /api/v1/... → 201 created
- POST /api/v1/... → 409 on conflict
- GET  /api/v1/... → 404 when missing

If the feature also extends another route (e.g. accepts an optional param),
state that too:

- POST /api/v1/other-route accepts optional `param_name` in body
- GET  /api/v1/other-route accepts `param_name` as query filter

## Configuration surface (the profile keys / env vars operators rely on)

Profile YAML keys, env vars, or other declarative configuration the feature
exposes to operators. Use this for features that are config-driven rather
than (or in addition to) REST-driven (engines, runtimes, daemons).

Skip if the feature has no operator-facing configuration.

- `agent.example_key: <type>` (default `<value>`) — what it does
- `ENV_VAR_NAME` — purpose, allowed values

## Event stream contract (what callers of the streaming API must handle)

For features that emit events into the agent's `StreamEvent` stream (or
another public event stream), list every event type callers must handle
as part of the public contract. Skip for features that don't emit stream
events.

- `EVENT_NAME` — when it fires, what's in the payload
- `OTHER_EVENT` — ...

## Extension points (for plugins / enterprise / external use)

Documented seams that other packages plug into. The spec-check skill verifies
the named functions/classes exist and are exposed at the documented path.

- `function_name` in `module.path` — what it overrides and when it's resolved

Skip this section if the feature has no documented extension points.

## Tests (must exist and pass)

Tests in the codebase tagged with `@pytest.mark.spec("<feature>.<item>")`.
The skill runs `pytest -m 'spec("...")'` per marker.

- spec("feature-slug.first_invariant")
- spec("feature-slug.second_invariant")

## Known gaps

Acknowledged-but-not-fixed gaps between spec intent and current code. The
skill reports these as info, not failure. Be specific — vague "needs work"
items don't help.

- Specific thing that is broken or missing on purpose, with context (one sentence)
- Another gap, optionally with tracking info: "Foo is missing — tracked in issue #NNN, eta 2026-MM"

## Cross-references

Navigational, not verified.

- related_spec: other-feature.md
- adr: ADR-NNN
- docs: docs/features/<this>.md (user guide)
- commit: <hash> (first introduction, optional)
