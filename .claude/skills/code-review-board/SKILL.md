---
name: code-review-board
description: |
  Run a repo-wide code analysis (bugs, security, architecture, concurrency, performance, code-smells) and create one GitHub issue per verified finding on the project board. Optimized for the pytaskforce repo + GitHub Project #3, but the workflow generalizes to any repo with a GitHub project board.

  Trigger this skill whenever the user asks for a code review that should produce board items: "mach eine code-analyse und leg issues an", "review den code und erzeuge board einträge", "schau dir den code an und finde probleme — pro finding einen issue", "audit the codebase", "find bugs and security issues across the repo", "/code-review-board". Even when the user phrases it less explicitly ("kannst du dir den code anschauen?" with context that suggests systematic review), prefer this skill over an ad-hoc analysis, because it produces traceable, board-tracked output and avoids the documented anti-patterns from prior sessions.
---

# Code Review → Board

This skill turns a broad code-review request into a structured set of GitHub issues on a project board. It exists because ad-hoc analysis tends to produce duplicates, drifting finding counts, gut-feel severities, and issues that the user has to manually sort afterwards. The playbook below is the result of a real session (2026-05-16) that produced 95 issues and the lessons learned from it.

## When this triggers

The skill applies when **all** of the following are true:

- The user wants a broad sweep, not a targeted "look at file X"
- The output should be GitHub issues on a project board, not just a list in chat
- The repo has a CLAUDE.md or similar architecture doc the agents can reference

If the user only wants a quick critique of one file or function, skip this skill and just read the file.

## Phase 0 — Calibrate scope and depth

Before doing any work, ask the user **one** question to set the cap:

> Wie tief soll der Review gehen?
> - **quick** — nur P0/P1 (security + critical bugs + layer violations), cap 30 issues total
> - **deep** — alles inkl. P2 code-smells, cap ~100 issues total (default)
> - **focused: <area>** — nur ein Bereich (z.B. "focused: security" oder "focused: api")

If they don't answer or say "egal", default to **deep**.

Also confirm the board target: `gh project view <NUMBER> --owner <OWNER>` should succeed before spending any compute on analysis. For pytaskforce the defaults are `--owner rudi77 --number 3`.

## Phase 1 — Free wins (deterministic, parallel)

Run these in parallel in **one** tool-call block before spawning any LLM agents. They're cheap, deterministic, and find ~20% of all findings without burning tokens:

```powershell
unset GITHUB_TOKEN  # see Conventions below
uv run ruff check src/ agents/*/src 2>&1 | tee tmp/review_ruff.txt
uv run mypy --strict src/taskforce 2>&1 | tee tmp/review_mypy.txt
```

In parallel, run pattern sweeps with the `Grep` tool (not bash grep):

| Pattern | Why |
|---|---|
| `except Exception:` | Likely bare except → bug |
| `Dict\[str, Any\]` | Should be dataclass/Pydantic |
| `time\.sleep\(` | Blocking in async code |
| `os\.getenv\("(.*TOKEN\|.*KEY\|.*SECRET)` | Secrets handling smell |
| `r"C:\\` or `/home/` or `/Users/` | Hardcoded paths |
| `TODO\|FIXME\|HACK\|XXX` | Pre-existing known issues |

Capture results in `tmp/code_review_findings_<date>.md` under a `## Free Wins` section. These become candidate findings — still subject to severity assessment and dedup in Phase 5.

## Phase 2 — Git hot-spots

Hot-spots are where bugs cluster. One command:

```powershell
git log --since="6 months ago" --pretty=format: --name-only `
  | Where-Object { $_ } `
  | Group-Object `
  | Sort-Object Count -Descending `
  | Select-Object -First 15 Count, Name
```

(Bash equivalent: `git log --since="6 months ago" --pretty=format: --name-only | sort | uniq -c | sort -rn | head -30`)

Hand the top-15 list to each Phase-4 agent as a "pay extra attention to these files" annotation.

## Phase 3 — Cross-cutting topics index

**Skip this phase if you're running with `focused: <single area>`** — there's only one agent, nothing to deduplicate against. Phase 3 only earns its keep when 2+ scopes overlap.

Before spawning multiple agents, write a **topics index** that assigns potentially-overlapping themes to exactly one agent scope. This prevents the duplication that ate cycles in the 2026-05-16 session (Wiki-Race and Tool-Result-Store were each found by two agents independently).

Default index for pytaskforce-style codebases:

| Theme | Owner scope |
|---|---|
| Wiki-Store / Memory race conditions | Infra-rest (persistence) |
| Tool-Result-Store TTL + race | Infra-LLM+tools |
| Layer-violations (core → app/infra) | Core |
| OAuth/PKCE/token-store security | Infra-rest (auth) |
| Gateway-route authentication | API+CLI |
| ContextManager / messages-list races | Core |
| ReAct-loop bugs | Core |

Add the index to the workspace markdown and embed it in each agent briefing.

## Phase 4 — Parallel Explore agents (one message, all at once)

Spawn **6–7 Explore agents in a single assistant turn**. Sequential spawning wastes ~5× the wall-clock time. Use `Explore` (read-only) — it has the right tools, is faster, and cheaper than `general-purpose`.

Scopes (no overlap, full coverage):

1. **Core** — `src/taskforce/core/domain/`, `src/taskforce/core/interfaces/`, `src/taskforce/core/tools/`, `src/taskforce/core/utils/`
2. **Infrastructure: LLM + Tools** — `src/taskforce/infrastructure/llm/`, `src/taskforce/infrastructure/tools/`
3. **Infrastructure: rest** — `src/taskforce/infrastructure/persistence/`, `communication/`, `scheduler/`, `auth/`, `event_sources/`, `rule_engine/`, `messaging/`, `runtime/`, `cache/`, `memory/`, `skills/`, `tracing/`, `acp/`
4. **Application** — `src/taskforce/application/`
5. **API + CLI** — `src/taskforce/api/`, `cli/src/taskforce_cli/`
6. **Agent packages** — `agents/butler/src/`, `agents/coding-agent/src/`, `agents/rag-agent/src/`, `agents/security-agent/`, `agents/swe-bench-agent/`, plus the configs/ YAMLs
7. **Tests** — `tests/` (test-smells, missing coverage for critical paths, mock-only tests masking bugs)

**Briefing template for every agent** (fill the bracketed bits):

```
You are a senior code reviewer. Find concrete problems (bugs, code smells,
performance, security, architecture violations, edge cases). DO NOT propose
fixes. DO NOT change code. Only identify.

**Scope (only search here):**
[absolute paths from the scope above]

**Architecture rules (violations = hard bugs):**
[paste the Import Matrix from CLAUDE.md for the relevant layer]

**Pay extra attention to these hot-spot files:**
[the top-15 list from Phase 2]

**Cross-cutting topics owned by other scopes (skip these):**
[the topics index from Phase 3, minus this agent's own topics]

**What to look for:**
1. Layer import violations (grep "from taskforce.infrastructure" in core/)
2. Magic strings instead of enums (should use core/domain/enums.py)
3. Dict[str, Any] instead of dataclass/Pydantic
4. Functions > 30 lines
5. Generic `except Exception:` without re-raise
6. Blocking I/O (open/time.sleep) in async code
7. Mutable default args
8. Missing type annotations on public APIs
9. Race conditions on shared mutable state without lock
10. Command injection, path traversal, SSRF in tools
11. Hardcoded paths / platform assumptions
12. TODO/FIXME/HACK comments (often real issues)
13. Dead code, unreachable paths
14. God classes (>500 LoC, >20 methods)
15. [add scope-specific items, e.g. for tools: tool_choice consistency,
    approval-risk-level, supports_parallelism with shared state]

**Per finding format:**
- **Title** (≤80 chars, German, precise)
- **Severity**: use the Impact×Likelihood matrix in the skill
- **Category**: bug | architecture | code-smell | performance | security |
  maintainability | concurrency
- **Files**: `path/to/file.py:LINE`
- **Description**: 2-4 sentences (problem + impact)
- **Evidence**: 5-15 line code snippet showing the issue

**Ignore:**
- Style issues Black/Ruff would auto-fix
- Documented ADR design decisions
- Micro-optimizations without realistic impact
- Anything already in your "skip" list above

**Cap: 25 findings max.** Pick the top problems. Better few precise than
many trivial.
```

## Phase 5 — Spot-check verification (parallel reads)

Before creating issues, **read the actual code** for the top-5 highest-severity findings to make sure they aren't hallucinated. One assistant turn, 5 parallel `Read` calls. If any finding falls apart on inspection, drop it from the list — better to lose a real one than to litter the board with a false positive.

## Phase 6 — Severity scoring (Impact × Likelihood)

Replace gut-feel with the matrix:

|  | Likelihood 1 (rare) | 2 (normal) | 3 (frequent) |
|---|---|---|---|
| **Impact 1** (annoying) | low | low | medium |
| **Impact 2** (data-loss / crash) | medium | high | high |
| **Impact 3** (RCE / data leak / spoofing) | high | **P0** | **P0** |

- **P0** maps to "must fix this sprint" — critical security and architectural violations
- **high** maps to "next sprint" — real bugs and concurrency issues
- **medium / low** maps to "backlog" — code smells and minor maintainability

This is reproducible. If the user later asks "why is X P0 and Y P1", the answer is the matrix.

## Phase 7 — Fix the findings list

Write **all** findings into `tmp/code_review_findings_<date>.md` with a stable numbering. Once that file is saved, do not add findings during the issue-create loop. This is the rule that prevents drift (the 2026-05-16 session planned 87 issues and ended at 95 because of inline nachschüsse).

If you discover something later, append it to the file as `## Late Additions` and create the issue separately at the end — but log that as drift in the session summary.

## Phase 8 — Labels (one-time setup)

Run once per repo (it's idempotent — failures on existing labels are fine):

```bash
unset GITHUB_TOKEN
gh label create security      --color "B60205" --description "Security finding" 2>/dev/null || true
gh label create concurrency   --color "D93F0B" --description "Race condition / concurrency" 2>/dev/null || true
gh label create performance   --color "FBCA04" --description "Performance issue" 2>/dev/null || true
gh label create architecture  --color "1D76DB" --description "Architecture / design violation" 2>/dev/null || true
gh label create code-smell    --color "C5DEF5" --description "Maintainability / refactor" 2>/dev/null || true
```

Use these when creating issues so the board can filter by category.

## Phase 9 — Issue creation (batched)

For every finding, render with this **template** (German body, English structure — pytaskforce convention):

```markdown
## Severity
**<Critical|High|Medium|Low>** — <Category>

## Files
- `<path>:<line>`
- [additional files if relevant]

## Problem
<2-4 sentences: what's wrong, why it's wrong, impact>

## Evidence
```<lang>
<5-15 lines of code showing the issue>
```

## Akzeptanzkriterien
- [ ] <concrete, testable item 1>
- [ ] <concrete, testable item 2>
- [ ] [test/regression item]
```

**Title prefixes** (drives filterability):

- `[SEC P0]`, `[SEC P1]`, `[SEC P2]` — security
- `[ARCH P0]`, `[ARCH P1]`, `[ARCH P2]` — architecture
- `[BUG P0]`, `[BUG P1]`, `[BUG P2]` — bugs
- `[CONC P0]`, `[CONC P1]`, `[CONC P2]` — concurrency
- `[PERF P1]`, `[PERF P2]` — performance
- `[SMELL]` — code smells (no P-tier, usually P2)

**Batching rule**: max **4 issues per Bash call**, chained sequentially:

```bash
unset GITHUB_TOKEN
PROJ="@<owner>'s <ProjectTitle>"   # e.g. "@rudi77's PyTaskforce"

gh issue create --title "<title>" --label "bug,security" --project "$PROJ" --body "$(cat <<'EOF'
<rendered template>
EOF
)" 2>&1 | tail -1

gh issue create ...  # 2nd
gh issue create ...  # 3rd
gh issue create ...  # 4th
```

`tail -1` keeps only the resulting URL so the user sees `https://github.com/<owner>/<repo>/issues/<N>` lines in order.

After all issues are created, set the board's Priority field (P0/P1/P2) on each created item. Skip this step if the board has no Priority field. The flow needs three lookups but only one of each is expensive:

```bash
unset GITHUB_TOKEN

# Step 1 — once per session: cache field+option ids
gh project field-list <N> --owner <OWNER> --format json `
  | python -c "
import json, sys
d = json.load(sys.stdin)
for f in d['fields']:
    if f['name'] == 'Priority':
        print('FID=' + f['id'])
        for o in f.get('options', []):
            print(o['name'] + '=' + o['id'])"
# also cache PROJECT_ID — it's in any item's `id` prefix or query via `gh project view <N> --owner <OWNER> --format json`

# Step 2 — once per session, AFTER all issues are created: bulk-resolve item-ids
gh project item-list <N> --owner <OWNER> --limit 500 --format json `
  | python -c "
import json, sys
created_numbers = {371, 372, 373, 374, 375}   # the issue numbers you got from gh issue create
for item in json.load(sys.stdin)['items']:
    num = item.get('content', {}).get('number')
    if num in created_numbers:
        print(f'{num}\t{item[\"id\"]}')"

# Step 3 — one item-edit call per issue (these are cheap but sequential)
gh project item-edit --project-id <PID> --id <ITEM_ID> --field-id <FID> --single-select-option-id <P1_OPT>
```

For 95 issues this is ~97 API calls — slow but bounded. Don't try to set the field inline during `gh issue create` (the CLI doesn't expose it). If you find yourself doing this often, add `scripts/set_priorities.py` that takes `{371:"P1", 372:"P0", ...}` JSON input and runs steps 2+3 in one shot.

**Watch out:** `gh project item-edit` returns no output on success. Check exit code, not stdout.

## Phase 10 — Verification

End the session with one verification call:

```bash
unset GITHUB_TOKEN
gh project item-list <N> --owner <OWNER> --limit 500 --format json `
  | jq '.items | map(select(.content.title | startswith("[SEC") or startswith("[ARCH") or startswith("[BUG") or startswith("[CONC") or startswith("[PERF") or startswith("[SMELL")))| length'
```

Compare against the count from the fixed findings file. If they don't match, surface the diff to the user — don't paper over it.

## Conventions

These are pytaskforce-specific defaults. If you're running the skill on a different repo, swap them out:

- **Project**: GitHub Project #3 "PyTaskforce" (owner `rudi77`)
- **Project title for `--project` flag**: `"@rudi77's PyTaskforce"`
- **Default profile language for issue bodies**: German (user is German-speaking; English is fine for titles and structural elements)
- **Architecture reference**: `CLAUDE.md` at repo root (Import Matrix is the source of truth)
- **Always `unset GITHUB_TOKEN` before any `gh` call** — there's a stale token in the env var; keyring auth is what works. (See user-memory `feedback_gh_clear_token`.) In PowerShell: `Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue`. From the Bash tool: `unset GITHUB_TOKEN` works directly — always run it as the first line of every Bash call that uses `gh`.
- **Don't suggest fixes inline.** This skill produces issues, not commits. The user has a separate `forge board-loop` workflow for the implementation phase.

## Anti-patterns (don't repeat these)

These are real mistakes from the 2026-05-16 session that produced 95 issues:

| Anti-pattern | Consequence | Avoided by |
|---|---|---|
| No cross-cutting topics index | Wiki-Race was found by two agents independently | Phase 3 — assign each theme to exactly one scope |
| Severity = "gut feel" | Can't justify P0 vs P1 when user asks | Phase 6 — Impact × Likelihood matrix |
| Findings list not fixed before create loop | Planned 87, ended at 95 because of nachschüsse | Phase 7 — write to file, then freeze |
| Priority field not set on board | User has to manually sort 95 items | Phase 9 — `gh project item-edit` after each create |
| `tests/` directory skipped | Test-smells and missing coverage invisible | Phase 4 — explicit agent #7 for tests |
| No labels created | Board can't filter by category | Phase 8 — one-time label setup |
| `gh` calls without `unset GITHUB_TOKEN` | 401 errors mid-loop | Conventions — every Bash call starts with unset |
| Issues created but never verified on board | Skip silently if `--project` flag misbehaves | Phase 10 — explicit count comparison |

## Output to the user at the end

End with a compact summary like the 2026-05-16 example:

```
## Code-Analyse abgeschlossen

**<N> Issues angelegt** auf Board <Project> (#<num>), Range **#<first> – #<last>**:

| Kategorie | Anzahl | Issue-Range |
|---|---|---|
| Security P0 | <n> | #<a>-#<b> |
| Security P1/P2 | <n> | #<a>-#<b> |
| Architecture | <n> | #<a>-#<b> |
| Concurrency | <n> | #<a>-#<b> |
| Bugs | <n> | #<a>-#<b> |
| Performance | <n> | #<a>-#<b> |
| Code-Smell | <n> | #<a>-#<b> |

**Die wichtigsten P0 Security-Issues kurz:**
- #<N> <one-line description>
- ...

**Empfehlung zur Reihenfolge:** <one paragraph: which P0 issues are
immediately exploitable, what's the suggested fix order>
```

This summary mirrors what the user got last time and what they signaled they liked — short, dense, actionable.

## Resources

- `scripts/free_wins_sweep.ps1` — one-shot Phase-1 runner (optional; create on first use)
- `scripts/render_issue_body.py` — helper that takes a findings-file row and emits the issue body markdown (optional; create when the inline heredocs become annoying)

Both scripts are optional; the skill works without them. Add them only when you find yourself doing the same thing more than twice across runs.

## Validation runs

| Date | Scope | Findings | Notes |
|---|---|---|---|
| 2026-05-16 | full (all scopes) | 95 issues (#276-#370) | Initial run; produced the playbook |
| 2026-05-16 | focused: tests, cap 5 | 5 issues (#371-#375) | Skill v1 validation. Hot-spot data correctly flagged eval_butler.py as priority — agent then sourced 2 of top-5 from there. Free wins (Phase 1) caught 6 candidate findings in ~10s without LLM. Spot-check (Phase 5) confirmed all 5 with 3 parallel reads, zero hallucinations. Friction: setting Priority field on items took 3 separate gh calls per item — improved in Phase 9 docs. |
