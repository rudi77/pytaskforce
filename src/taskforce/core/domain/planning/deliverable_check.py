"""Pre-finalize deliverable check (issue #405 / QW1).

When the user's mission explicitly names output files (``"save your report
to ``boot_report.md``"``, ``"write it to ``iris_summary.md``"``), this
module helps the ReAct loop notice that those files were never created
before declaring the mission complete, and inject one extra reflection
step so the LLM can still produce them.

The heuristics are deliberately conservative — false positives would
prevent legitimate completions, false negatives are merely a missed
opportunity. We require:

* backtick-quoted filename with a known output extension, AND
* an action verb (save / write / create / produce / output / store /
  generate / emit) within ``_PROXIMITY_CHARS`` of the filename.

Filenames that appear only with read-style verbs (analyze, read, parse,
…) are ignored — those are inputs, not deliverables.
"""

from __future__ import annotations

import re
from pathlib import Path

_DELIVERABLE_VERBS = (
    "save",
    "saved",
    "saves",
    "write",
    "written",
    "writes",
    "create",
    "creates",
    "created",
    "produce",
    "produces",
    "produced",
    "output",
    "outputs",
    "store",
    "stores",
    "stored",
    "generate",
    "generates",
    "generated",
    "emit",
    "emits",
    "emitted",
)
_VERB_RE = re.compile(r"\b(?:" + "|".join(_DELIVERABLE_VERBS) + r")\b", re.IGNORECASE)

_FILENAME_RE = re.compile(
    r"`("
    r"[\w./\\:\-]+\."
    r"(?:md|markdown|txt|json|jsonl|py|csv|tsv|html|yml|yaml|toml|xml|sql|sh|log|ics|ipynb)"
    r")`"
)

_DIR_RE = re.compile(
    r"`("
    # Windows-style absolute path, either backslash or forward-slash form
    r"[A-Za-z]:[\\/](?:[\w.\-]+[\\/])*[\w.\-]+"
    # POSIX-style absolute path
    r"|/(?:[\w.\-]+/)+[\w.\-]+"
    r")`"
)

# Verb→filename window. Tight enough that
# ``"I have CSV `iris_flowers.csv` …[~200 chars]… write it to `iris_summary.md`"``
# does not mis-detect the input as a deliverable.
_PROXIMITY_CHARS = 120


def extract_deliverables(mission: str | None) -> list[str]:
    """Return filenames the mission explicitly asks the agent to write.

    Each returned name is the literal backtick-quoted text from the
    prompt — typically a basename (``report.md``) but may include a
    relative subpath (``out/summary.json``).
    """
    if not mission:
        return []
    files = list(_FILENAME_RE.finditer(mission))
    if not files:
        return []
    verbs = [m.start() for m in _VERB_RE.finditer(mission)]
    out: list[str] = []
    seen: set[str] = set()
    for m in files:
        if any(abs(m.start() - v) < _PROXIMITY_CHARS for v in verbs):
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def extract_candidate_dirs(mission: str | None) -> list[Path]:
    """Return backtick-quoted absolute directory paths from the mission.

    These are used as additional search roots when checking whether a
    deliverable exists. PinchBench prompts embed the per-mission temp
    workspace as an absolute path (``Your task workspace is
    `C:\\...\\pinchbench_ws_XXXX```), and the agent writes the
    deliverable there rather than into the project workspace.
    """
    if not mission:
        return []
    return [Path(m.group(1)) for m in _DIR_RE.finditer(mission)]


def find_missing(deliverables: list[str], search_roots: list[Path]) -> list[str]:
    """Return the subset of ``deliverables`` that exist in NONE of the roots.

    For each deliverable we check ``root/<deliverable>`` (handles
    relative subpaths) and ``root/<basename>`` (handles agents that
    flatten subpaths).
    """
    if not deliverables or not search_roots:
        return list(deliverables)
    missing: list[str] = []
    for name in deliverables:
        rel = Path(name)
        if not any(
            (root / rel).exists() or (root / rel.name).exists() for root in search_roots
        ):
            missing.append(name)
    return missing


def build_nudge(missing: list[str]) -> str:
    """One-line system reminder injected when deliverables are still missing."""
    files = ", ".join(f"`{m}`" for m in missing)
    return (
        "[System: The user explicitly asked you to write the following "
        f"file(s) but they do not exist on disk: {files}. Use the "
        "`file_write` or `edit` tool to create them now. Do not declare "
        "the task complete until they exist.]"
    )
