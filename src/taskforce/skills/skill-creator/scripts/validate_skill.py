"""Validate a Taskforce SKILL.md file using the framework parser.

Usage:
    python validate_skill.py <path-to-SKILL.md>

Exit codes:
    0 — valid
    1 — invalid (parser error printed to stderr)
    2 — argument or IO error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from taskforce.infrastructure.skills.skill_parser import (
    SkillParseError,
    parse_skill_markdown,
)


def _resolve_skill_path(raw: str) -> Path:
    """Accept either a SKILL.md file or a directory containing one."""
    path = Path(raw).expanduser().resolve()
    if path.is_dir():
        candidate = path / "SKILL.md"
        if not candidate.is_file():
            raise FileNotFoundError(f"Directory has no SKILL.md: {path}")
        return candidate
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Taskforce SKILL.md file.")
    parser.add_argument("skill_path", help="Path to SKILL.md or its directory")
    args = parser.parse_args(argv)

    try:
        skill_file = _resolve_skill_path(args.skill_path)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {skill_file}: {exc}", file=sys.stderr)
        return 2

    try:
        skill = parse_skill_markdown(content, str(skill_file.parent))
    except SkillParseError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 1

    print(f"ok: {skill.name} (type={skill.skill_type.value}) at {skill_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
