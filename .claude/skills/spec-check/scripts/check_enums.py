#!/usr/bin/env python3
"""Extract all enum class members from a Python file.

Reads a Python file with the stdlib `ast` module, finds every class that
inherits from `Enum` (directly or via `str, Enum` etc.), and emits a JSON
map of `{class_name: [member_names...]}`.

Used by the spec-check skill to verify `Event stream contract` claims like
`LLM_STREAM_RESTART` against the actual `core/domain/enums.py` definitions.

Stdlib only.

Usage:
    python check_enums.py src/taskforce/core/domain/enums.py
    python check_enums.py src/taskforce/core/domain/enums.py > /tmp/enums.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def _inherits_enum(class_def: ast.ClassDef) -> bool:
    """True if any base is named 'Enum' (or *Enum like IntEnum, StrEnum)."""
    for base in class_def.bases:
        if isinstance(base, ast.Name) and base.id.endswith("Enum"):
            return True
        if isinstance(base, ast.Attribute) and base.attr.endswith("Enum"):
            return True
    return False


def _extract_members(class_def: ast.ClassDef) -> list[str]:
    """Names of class-level assignments (`MEMBER = "value"`)."""
    members: list[str] = []
    for stmt in class_def.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    members.append(target.id)
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id.isupper():
                members.append(stmt.target.id)
    return members


def extract(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    result: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _inherits_enum(node):
            result[node.name] = _extract_members(node)
    return result


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) != 2:
        print("usage: check_enums.py <path/to/enums.py>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    enums = extract(path)
    json.dump(enums, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
