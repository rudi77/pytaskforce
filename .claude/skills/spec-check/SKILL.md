---
name: spec-check
description: |
  Verify every spec in docs/spec/ against the live codebase and report drift, regressions, and silent deletions. Each spec is the contract for one subsystem (CoWork, Gateway, ReAct loop, etc.); this skill parses each claim (API surface, configuration, event streams, extension points, tests, capabilities, invariants) and checks it against the code. Drift fails loud as P0/P1/P2 findings; acknowledged gaps stay quiet.

  Trigger this skill whenever the user wants to validate the spec layer: "check the specs", "did anything regress?", "run spec-check", "audit feature drift", "is the gateway still doing what the spec says", "/spec-check", "spec-check --feature cowork", "verify that we didn't break anything", or after a refactor where contracts could have shifted. Prefer this skill over an ad-hoc grep because it follows the documented verification model and produces a reproducible, severity-scored report.
---

# spec-check

Reads `docs/spec/*.md` and verifies every claim against the current codebase.
Each spec describes one subsystem from the user's perspective; this skill is
the enforcer that catches the moment reality starts to drift from the
written contract.

The pattern is the same as `code-review-board`: deterministic checks first,
LLM-driven checks for behavior invariants, optional board-issue creation
at the end. The output is `tmp/spec_check_<date>.md` — read it, fix the
real problems, update the spec where intent has changed.

## When this triggers

- After any refactor where existing contracts might have shifted
- Before a release — gate the cut on a clean spec-check run
- When the user is unsure whether a feature is still working as documented
- Periodically (e.g. weekly cron) to catch silent drift
- As the verification step after `code-review-board` produced a wave of changes

If the user only wants to know "does CoWork work right now", scope with
`--feature cowork`. Don't full-scan when one feature is enough — full scans
spawn ~30 sub-agents and burn meaningful token budget.

## Conventions

These come from prior memories — do not break them:

- **`unset GITHUB_TOKEN` before any `gh` call.** The env var holds a stale
  token; keyring auth is what works. Always first line of every Bash call
  that uses `gh`. PowerShell equivalent: `Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue`.
- **Board is GitHub Project #3 "PyTaskforce" (owner rudi77).** Issue title format `[SPEC-DRIFT P0] <feature>: <claim>`. Always set Priority field after creation.
- **Default is NO board issues.** `--create-issues` is opt-in. The user should look at the report first.
- **Don't propose fixes inline.** This skill verifies and reports. Fixes happen via the normal `forge board-loop` workflow after the user triages the report.
- **Agent packages (Butler, Coding, RAG) are explicitly excluded** from spec coverage — see `feedback_agents_out_of_spec`. Don't try to verify them; they aren't specced.

## Phase 0 — Arguments + setup

Parse the user's arguments:

| Flag | Behavior |
|---|---|
| (none) | Verify all specs in `docs/spec/*.md`, no issues created |
| `--feature <slug>` | Scope to one spec (e.g. `--feature cowork`) |
| `--quick` | Skip Phase 3 (LLM behavior checks) — deterministic only, ~10× faster, ~0 tokens |
| `--create-issues` | After report, create board issues for each P0/P1 finding |
| `--max-llm-per-spec <N>` | Cap LLM checks per spec (default 15; lower for cost control) |

Setup:

```bash
# Verify board access if --create-issues
unset GITHUB_TOKEN
gh project view 3 --owner rudi77 --format json > /dev/null
```

Create the output dir if missing:

```bash
mkdir -p tmp
```

## Phase 1 — Parse specs

For every spec file (`docs/spec/<feature>.md` excluding `README.md`,
`_template.md`, `index.md`), call the parser:

```bash
python .claude/skills/spec-check/scripts/parse_spec.py docs/spec/cowork.md > /tmp/spec_<feature>.json
```

The parser emits structured JSON:

```json
{
  "feature": "cowork",
  "status": "shipped",
  "since": "2026-05-15",
  "last_verified": "2026-05-16",
  "owner": "rudi77",
  "adr": "",
  "api_routes": [
    {"method": "POST", "path": "/api/v1/projects", "status": 201, "condition": "created"},
    {"method": "POST", "path": "/api/v1/projects", "status": 409, "condition": "on duplicate path"}
  ],
  "config_keys": [
    {"profile": "default", "key": "agent.example_key", "default": "value"}
  ],
  "event_names": ["INTERRUPTED", "STREAM_RESTART"],
  "extension_points": ["set_project_store_override"],
  "test_markers": ["cowork.create_scratch_creates_anchors", "..."],
  "capabilities": ["create a project from scratch ...", "..."],
  "invariants": ["Two projects cannot point at the same on-disk directory ...", "..."],
  "known_gaps": ["No archive endpoint ...", "..."]
}
```

If the parser fails on a spec file, log the parse error and skip that spec
with a clear marker in the final report (so the user can fix the spec).

## Phase 2 — Deterministic checks (parallel)

For each spec, run these checks **in parallel where possible**. They are
cheap, deterministic, and produce reproducible verdicts.

### 2a — API surface

Call the route extractor:

```bash
python .claude/skills/spec-check/scripts/check_routes.py src/taskforce/api/routes/ > /tmp/registered_routes.json
```

Output is a list of all registered (method, path) pairs from FastAPI
decorators across the routes directory. For each `api_routes[]` claim in
each spec:

- Match against registered routes. **PASS** if (method, path) exists.
- **FAIL** if the route is missing entirely — that's a regression.
- For documented status codes: if the route exists, scan its `responses=` dict and `status_code=` param. PASS if the status is documented, WARN if not.

### 2b — Configuration surface

For each `config_keys[]` claim, load the referenced YAML profile and check
the dotted path:

```bash
python -c "
import yaml, sys
p = yaml.safe_load(open('src/taskforce/configs/default.yaml'))
# walk dotted path
keys = 'agent.example_key'.split('.')
v = p
for k in keys: v = v.get(k) if isinstance(v, dict) else None
print(v)
"
```

- PASS if key exists at path. If default value claimed, additionally check match.
- FAIL if key missing.

Profile resolution: framework profiles live in `src/taskforce/configs/`,
agent-package profiles in `agents/*/configs/`. The parser preserves the
profile name; the check needs to glob both locations.

### 2c — Event stream contract

Call the enum extractor:

```bash
python .claude/skills/spec-check/scripts/check_enums.py src/taskforce/core/domain/enums.py > /tmp/event_enums.json
```

For each event name claimed (e.g. `INTERRUPTED`, `LLM_STREAM_RESTART`):

- PASS if the name is a member of one of the enums (`EventType`, `LLMStreamEventType`, etc.)
- FAIL if not — either the spec is wrong or the event was removed.

### 2d — Extension points

For each claimed function/class symbol, grep the codebase:

```python
# Use the Grep tool with pattern like:
#   "^(def |class |async def )<symbol>\b"
# in path: src/taskforce/
```

- PASS if found.
- FAIL if not found at all.
- WARN if found but in an unexpected location (drift hint).

### 2e — Tests

For each `test_markers[]` claim:

```bash
uv run pytest --collect-only -q -m "spec(\"<marker_name>\")" 2>&1 | tail -5
```

Parse the output:
- PASS if at least one test collected.
- FAIL ("missing") if no test collected — spec asserts coverage that doesn't exist.

Then optionally **run** the collected tests:

```bash
uv run pytest -m "spec(\"<marker_name>\")" --tb=no -q 2>&1 | tail -3
```

- PASS if all pass.
- FAIL if any test failed.

**Cost control:** if `--quick`, skip the run step. Just collect.

## Phase 3 — LLM behavior checks (parallel sub-agents)

For each spec, spawn **one Explore sub-agent** that verifies all the
capability + invariant claims in one shot. Don't spawn one agent per claim
— that explodes the agent count (30 specs × ~10 claims = 300 agents).

Cap: at most `--max-llm-per-spec` claims per agent (default 15). If a
spec has more, take the first 15 (they're usually the most important).

Spawn pattern (parallel — all specs at once in one assistant message):

```
Agent({
  description: "Verify spec: <feature>",
  subagent_type: "Explore",
  prompt: <see template below>
})
```

**Agent prompt template:**

```
You are verifying a Taskforce spec against the live codebase. You produce
structured JSON only — no prose, no markdown, no apologies.

**Spec to verify:** docs/spec/<feature>.md (read this first, completely)

**Your task:** For each Capability and each Invariant in the spec, find
the code that implements it and decide whether the claim still holds.

**Verdicts:**
- PASS — the code clearly implements the claim. Cite file:line.
- FAIL — the code contradicts the claim, or the claimed mechanism is missing. State what's missing.
- UNCERTAIN — you can't tell from the code (claim is ambiguous, code is too scattered, evidence is partial). State what made you uncertain.

**Rules:**
- Do not propose fixes. Verify only.
- Cite specific file:line for every PASS and FAIL. Vague answers fail the spec.
- Don't hallucinate file paths. If you can't find the file, FAIL with "no file found for claim".
- Don't grade Known gaps — they're acknowledged, skip them.
- Cap: verify at most the first <N> capabilities and the first <N> invariants. Skip overflow with verdict "SKIPPED".

**Output format (must be valid JSON, no other text):**
{
  "feature": "<feature-slug>",
  "capabilities": [
    {"claim": "<exact text>", "verdict": "PASS|FAIL|UNCERTAIN|SKIPPED", "evidence": "<file:line or reason>"}
  ],
  "invariants": [
    {"claim": "<exact text>", "verdict": "PASS|FAIL|UNCERTAIN|SKIPPED", "evidence": "<file:line or reason>"}
  ]
}
```

Spawning all specs in parallel in ONE assistant message is critical — this
is the slowest phase by far. Group into batches of 6-8 if the runtime
complains about too many concurrent agents.

After all agents return, parse each JSON response. If a response is
malformed (not valid JSON, missing fields), mark every claim in that spec
as UNCERTAIN with reason "agent response unparseable" — don't crash.

## Phase 4 — Aggregate + severity

For each finding, apply the severity matrix:

| Finding type | Severity | Why |
|---|---|---|
| API route claimed but not registered | **P0** | API contract violation |
| API route returns wrong/missing status code | P1 | client may handle wrong |
| Config key claimed but missing | P1 | config drift |
| Config default value mismatch | P2 | doc out of sync |
| Event name claimed but not in enum | P1 | event contract drift |
| Extension point symbol not found | P1 | plugin contract broken |
| Test marker claimed but no test collected | P1 | spec asserts coverage missing |
| Test marker collected but tests fail | **P0** | direct regression |
| Capability LLM verdict FAIL | **P0** | feature broken |
| Invariant LLM verdict FAIL — security/data-loss keyword | **P0** | critical |
| Invariant LLM verdict FAIL — UX/maintainability | P1 | important |
| Invariant LLM verdict UNCERTAIN | P2 | spec ambiguous, rewrite |
| Capability LLM verdict UNCERTAIN | P2 | spec ambiguous |
| `last_verified` older than 30 days | **info** | spec aging warning |
| Known gap item | **info** | acknowledged |

Heuristic for invariant FAIL severity: search the claim for keywords
`security|auth|token|leak|data|secret|delete|cascade|race|deadlock|crash`
→ P0. Otherwise P1. Imperfect but reproducible; the user can re-grade
on review.

## Phase 5 — Markdown report

Write to `tmp/spec_check_<YYYY-MM-DD>_<HHMMSS>.md`. Structure:

```markdown
# Spec-Check Report — 2026-05-16 14:30

**Specs checked:** 30 / 30
**Total claims verified:** 740 (210 mechanical + 320 capabilities + 210 invariants)
**Findings:** 4 P0, 12 P1, 8 P2, 5 info

## Summary table

| Feature | Status | Mech | Caps | Inv | Verdict |
|---|---|---|---|---|---|
| cowork | shipped | 10/10 | 5/6 | 7/7 | DRIFT (1 cap UNCERTAIN) |
| gateway | shipped | 13/13 | 7/7 | 7/9 | REGRESSION (2 inv FAIL — see #N) |
| ... |

## Findings

### P0 — gateway: "Webhook signature verification ALWAYS runs before any agent code"
**Source:** gateway.md → Invariants
**Verdict:** FAIL
**Evidence:** src/taskforce/api/routes/gateway.py:301-319 — verify_signature can return True on missing token (#286 in Known gaps but the spec text is unconditional)
**Suggested action:** Either tighten the invariant text to acknowledge fail-open, or fix the adapter to fail-closed.

[... repeat per finding, P0 first then P1 then P2 then info]

## Last-verified warnings

These specs haven't been re-verified in >30 days:
- (none)

## Per-feature details

[collapsed sections per feature with all claim verdicts including PASS]
```

The summary table at the top is for skim-reading; the per-feature detail
section is for the user when they pick what to fix.

## Phase 6 — Optional board-issue creation (`--create-issues`)

Same playbook as `code-review-board`:

```bash
unset GITHUB_TOKEN

# Ensure spec-drift label exists (idempotent)
gh label create spec-drift --color "5319E7" --description "Drift between docs/spec and code" 2>/dev/null || true

# Per P0/P1 finding (in batches of 4 per Bash call):
gh issue create \
  --title "[SPEC-DRIFT P0] <feature>: <one-line claim>" \
  --label "bug,spec-drift" \
  --project "@rudi77's PyTaskforce" \
  --body "$(cat <<'EOF'
## Severity
**Critical** — Spec Drift

## Spec
`docs/spec/<feature>.md` → <section> → <claim text>

## What spec-check found
<verdict + evidence>

## Suggested action
<one-line: fix code OR update spec>

## Akzeptanzkriterien
- [ ] Either: code change so the claim holds again
- [ ] Or: spec update reflecting the new contract (with rationale)
- [ ] Re-run spec-check → claim PASSes
EOF
)" 2>&1 | tail -1
```

After each batch of 4 issues, set Priority field on the board (P0/P1/P2)
using the same 3-step flow as code-review-board (cache field IDs → resolve
item IDs → bulk item-edit).

**P2 + info findings:** report only, don't create issues. They'd be noise.

## Phase 7 — last_verified warnings

If a spec's frontmatter `last_verified:` is older than 30 days from today's
date, list it in the report. Spec is probably stale even if checks pass —
nudge the user to do a refresh review.

If the spec has zero FAIL findings AND the user is running interactively,
offer: "Bump last_verified for these N specs to today?" — don't auto-bump,
that's confidence inflation.

## Output format — what the user sees at the end

End with a compact summary like `code-review-board` does:

```
## Spec-Check abgeschlossen

**30 Specs geprüft.** Range #<first> – #<last> bei --create-issues.

| Severity | Count |
|---|---|
| P0 (regression / critical drift) | 4 |
| P1 (drift / missing coverage) | 12 |
| P2 (ambiguous / minor) | 8 |
| info (known gaps + aging) | 5 |

**Die P0-Findings:**
- gateway: <one-line>
- ...

**Empfehlung:** <pick the top 1-2 fixes by impact>

Report: tmp/spec_check_2026-05-16_143012.md
```

## Anti-patterns (don't do these)

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Spawning one Explore agent per claim | 30 specs × 10 claims = 300 agents, blows up cost | One agent per spec, batch claims |
| Creating board issues without `--create-issues` | Surprise board pollution | Opt-in flag is mandatory |
| Treating UNCERTAIN as PASS | Drift hides | UNCERTAIN is P2 finding — surface it |
| Trying to verify agent packages (Butler/Coding/RAG) | They aren't specced; you'll just say "no spec found" | Skip them; the index documents the exclusion |
| Hardcoding feature names | Spec list is data, not code | Always glob `docs/spec/*.md` |
| Skipping `unset GITHUB_TOKEN` in any gh call | Auth fails mid-loop | First line of every Bash call |
| Letting parse errors crash the whole run | One bad spec kills the report | Catch + log + skip + flag in report |

## Validation runs

| Date | Scope | Findings | Notes |
|---|---|---|---|
| 2026-05-16 | initial smoke test on cowork.md | (record after first run) | First end-to-end verification of skill + scripts |
