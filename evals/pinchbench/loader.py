"""Pinchbench task loader.

Clones the upstream pinchbench/skill repository on demand (shallow) and
parses the markdown task files into ``PinchbenchTask`` records.

Task format (see https://github.com/pinchbench/skill/blob/main/tasks/TASK_TEMPLATE.md):

    ---
    id: task_xxx
    name: ...
    category: productivity
    grading_type: automated | llm_judge | hybrid
    timeout_seconds: 300
    workspace_files: []          # optional fixtures from skill/assets/
    multi_session_prompts: []    # optional list of follow-up prompts
    ---

    ## Prompt
    <user prompt>

    ## Expected Behavior
    <description>

    ## Grading Criteria
    <checklist>

    ## Automated Checks
    ```python
    def grade(transcript: list, workspace_path: str) -> dict: ...
    ```

    ## LLM Judge Rubric
    <markdown rubric>
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

EVAL_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVAL_DIR / "skill"
UPSTREAM_REPO = "https://github.com/pinchbench/skill.git"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_PYTHON_BLOCK_RE = re.compile(r"```python\s*\n(.*?)\n```", re.DOTALL)


@dataclass
class PinchbenchTask:
    """Parsed view of a single pinchbench task markdown file."""

    id: str
    name: str
    category: str
    grading_type: str  # automated | llm_judge | hybrid
    timeout_seconds: int
    workspace_files: list[str] = field(default_factory=list)
    multi_session_prompts: list[dict] = field(default_factory=list)
    prompt: str = ""
    expected_behavior: str = ""
    grading_criteria: str = ""
    grade_function: str = ""  # raw `def grade(...)` source extracted from markdown
    llm_judge_rubric: str = ""
    source_path: Path | None = None
    raw_frontmatter: dict = field(default_factory=dict)


def ensure_skill_checkout(update: bool = False) -> Path:
    """Clone or refresh the upstream skill repo into ``SKILL_DIR``."""
    if not SKILL_DIR.exists():
        print(f"[pinchbench] cloning {UPSTREAM_REPO} into {SKILL_DIR} ...")
        subprocess.run(
            ["git", "clone", "--depth", "1", UPSTREAM_REPO, str(SKILL_DIR)],
            check=True,
        )
    elif update:
        print(f"[pinchbench] updating checkout at {SKILL_DIR} ...")
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin"], cwd=SKILL_DIR, check=True
        )
        subprocess.run(
            ["git", "reset", "--hard", "origin/HEAD"], cwd=SKILL_DIR, check=True
        )
    return SKILL_DIR


def _parse_sections(body: str) -> dict[str, str]:
    """Split a markdown body into a ``{lower-heading: text}`` dict."""
    sections: dict[str, str] = {}
    headings: list[tuple[str, int, int]] = []
    for match in _SECTION_RE.finditer(body):
        headings.append((match.group(1).strip().lower(), match.start(), match.end()))
    for i, (heading, _, end) in enumerate(headings):
        next_start = headings[i + 1][1] if i + 1 < len(headings) else len(body)
        sections[heading] = body[end:next_start].strip()
    return sections


def parse_task(path: Path) -> PinchbenchTask:
    """Parse a single ``task_*.md`` file."""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"No YAML frontmatter in {path}")

    frontmatter = yaml.safe_load(m.group(1)) or {}
    sections = _parse_sections(m.group(2))

    grade_func = ""
    auto_section = sections.get("automated checks", "")
    if auto_section:
        py_match = _PYTHON_BLOCK_RE.search(auto_section)
        if py_match:
            grade_func = py_match.group(1).strip()

    return PinchbenchTask(
        id=str(frontmatter.get("id", path.stem)),
        name=str(frontmatter.get("name", path.stem)),
        category=str(frontmatter.get("category", "unknown")),
        grading_type=str(frontmatter.get("grading_type", "llm_judge")),
        timeout_seconds=int(frontmatter.get("timeout_seconds", 300)),
        workspace_files=list(frontmatter.get("workspace_files") or []),
        multi_session_prompts=list(frontmatter.get("multi_session_prompts") or []),
        prompt=sections.get("prompt", ""),
        expected_behavior=sections.get("expected behavior", ""),
        grading_criteria=sections.get("grading criteria", ""),
        grade_function=grade_func,
        llm_judge_rubric=sections.get("llm judge rubric", ""),
        source_path=path,
        raw_frontmatter=frontmatter,
    )


def _load_manifest(tasks_dir: Path) -> dict:
    manifest_path = tasks_dir / "manifest.yaml"
    if not manifest_path.exists():
        return {}
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}


def _str_list(value: object) -> list[str]:
    """Coerce a manifest section to a list of strings, dropping unknowns."""
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str)]
    if isinstance(value, str):
        return [value]
    return []


def load_tasks(
    suite: str = "all",
    *,
    limit: int | None = None,
    update: bool = False,
) -> list[PinchbenchTask]:
    """Return parsed tasks for the requested suite.

    ``suite`` accepts:
      - ``"all"`` / ``"full"`` — every task in ``tasks/``
      - ``"core"`` — task IDs listed under ``core`` (plus ``run_first``)
        in ``manifest.yaml``
      - any category name (e.g. ``"coding"``, ``"productivity"``) — tasks
        whose frontmatter ``category`` matches
      - a comma-separated list of explicit task IDs
    """
    skill_dir = ensure_skill_checkout(update=update)
    tasks_dir = skill_dir / "tasks"
    if not tasks_dir.exists():
        raise FileNotFoundError(f"tasks/ not found in {skill_dir}")

    all_files = sorted(tasks_dir.glob("task_*.md"))
    by_id = {p.stem: p for p in all_files}

    selected: Iterable[Path]
    suite_norm = suite.strip().lower()

    if suite_norm in {"all", "full"}:
        selected = all_files
    elif suite_norm == "core":
        manifest = _load_manifest(tasks_dir)
        core_ids = _str_list(manifest.get("run_first")) + _str_list(manifest.get("core"))
        # Deduplicate while preserving manifest order.
        seen: set[str] = set()
        selected = []
        for tid in core_ids:
            if tid in seen or tid not in by_id:
                continue
            seen.add(tid)
            selected.append(by_id[tid])
    elif "," in suite:
        ids = [s.strip() for s in suite.split(",") if s.strip()]
        selected = [by_id[t] for t in ids if t in by_id]
    else:
        # Treat as a category filter; parse-then-filter.
        parsed = [parse_task(p) for p in all_files]
        result = [t for t in parsed if t.category.lower() == suite_norm]
        if limit:
            result = result[:limit]
        return result

    tasks = [parse_task(p) for p in selected]
    if limit:
        tasks = tasks[:limit]
    return tasks
