#!/usr/bin/env python3
"""Parse a Taskforce spec file into structured JSON.

Reads a `docs/spec/<feature>.md` file and emits a JSON document with:
- frontmatter (feature, status, since, last_verified, owner, adr)
- api_routes:       list of {method, path, status, condition}
- config_keys:      list of {profile, key, default}
- event_names:      list of event-enum member names
- extension_points: list of symbol names
- test_markers:     list of marker strings (without spec("...") wrapper)
- capabilities:     list of free-text strings
- invariants:       list of free-text strings
- known_gaps:       list of free-text strings
- cross_refs:       list of free-text strings
- parse_errors:     list of warnings (the parser keeps going on minor issues)

Usage:
    python parse_spec.py docs/spec/cowork.md
    python parse_spec.py docs/spec/cowork.md > /tmp/cowork.json

The parser is permissive: anything that doesn't match a structured pattern
falls back to its raw bullet text. The spec-check skill treats unparsed
items as UNCERTAIN.

Stdlib only — no PyYAML dependency.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# ---------- Frontmatter ----------


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML-ish frontmatter as a dict; return (frontmatter, body)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    body = text[match.end():]
    fm: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        fm[key] = value
    return fm, body


# ---------- Section splitting ----------


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _split_sections(body: str) -> dict[str, str]:
    """Split body into {section_name: section_body} keyed by H2 heading.

    Section names are normalised to lowercase + underscore form:
      "## Capabilities (what the user can do)" -> "capabilities"
      "## API surface (the contract...)"        -> "api_surface"
      "## Known gaps"                            -> "known_gaps"
    """
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        raw_name = m.group(1).strip()
        norm = _normalise_section_name(raw_name)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[norm] = body[start:end].strip()
    return sections


def _normalise_section_name(raw: str) -> str:
    """e.g. 'API surface (the contract...)' -> 'api_surface'."""
    # drop parenthesised qualifier
    name = re.sub(r"\(.*?\)", "", raw).strip()
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name


# ---------- Bullet extraction ----------


_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)(?:\n\s{2,}.*)*$", re.MULTILINE)


def _bullets(section_body: str) -> list[str]:
    """Extract top-level bullet items (collapsing wrapped continuation lines).

    A bullet that continues on indented lines is joined with a single space.
    Sub-bullets (more than 2 spaces of indent) are NOT included as top-level
    items; they become part of the parent's text (caller can re-parse).
    """
    items: list[str] = []
    current: list[str] | None = None
    for line in section_body.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if not stripped:
            if current is not None:
                items.append(" ".join(current).strip())
                current = None
            continue
        if stripped.startswith(("- ", "* ")) and indent <= 2:
            if current is not None:
                items.append(" ".join(current).strip())
            current = [stripped[2:].rstrip()]
        elif current is not None:
            current.append(stripped.rstrip())
    if current is not None:
        items.append(" ".join(current).strip())
    return items


# ---------- Section parsers ----------


_HTTP_METHODS = "GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS"

_ROUTE_RE = re.compile(
    rf"^(?P<method>{_HTTP_METHODS})\s+(?P<path>/\S+)\s*"
    r"(?:→|->)\s*(?P<status>\d{3})(?:\s+(?P<condition>.+))?$"
)
_ROUTE_ACCEPT_RE = re.compile(
    rf"^(?P<method>{_HTTP_METHODS})\s+(?P<path>/\S+)\s+accepts\s+(?P<param_desc>.+)$"
)


def _parse_api_routes(bullets: list[str]) -> tuple[list[dict], list[str]]:
    routes: list[dict] = []
    errors: list[str] = []
    for raw in bullets:
        m = _ROUTE_RE.match(raw)
        if m:
            routes.append(
                {
                    "kind": "route",
                    "method": m.group("method"),
                    "path": m.group("path"),
                    "status": int(m.group("status")),
                    "condition": (m.group("condition") or "").strip(),
                    "raw": raw,
                }
            )
            continue
        m2 = _ROUTE_ACCEPT_RE.match(raw)
        if m2:
            routes.append(
                {
                    "kind": "accept",
                    "method": m2.group("method"),
                    "path": m2.group("path"),
                    "param_desc": m2.group("param_desc").strip(),
                    "raw": raw,
                }
            )
            continue
        errors.append(f"unparsed API-surface item: {raw}")
    return routes, errors


_CONFIG_KEY_RE = re.compile(
    r"`(?P<key>[A-Za-z_][A-Za-z0-9_.]*)"
    r"(?:\s*:\s*(?P<type>[^`]+?))?"
    r"`"
    r"(?:\s*\(default\s*[`\"]?(?P<default>[^`\")]+?)[`\"]?\))?"
)
_ENV_VAR_RE = re.compile(r"`(?P<env>[A-Z_][A-Z0-9_]*)`")


def _parse_config_keys(bullets: list[str]) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    for raw in bullets:
        # try env var first (all-uppercase backticked)
        env_match = _ENV_VAR_RE.match(raw.strip())
        if env_match and env_match.group("env").isupper():
            items.append({"kind": "env_var", "name": env_match.group("env"), "raw": raw})
            continue
        # try dotted profile key
        key_match = _CONFIG_KEY_RE.search(raw)
        if key_match:
            items.append(
                {
                    "kind": "profile_key",
                    "key": key_match.group("key"),
                    "default": (key_match.group("default") or "").strip() or None,
                    "raw": raw,
                }
            )
            continue
        errors.append(f"unparsed config item: {raw}")
    return items, errors


_EVENT_NAME_RE = re.compile(r"^`?(?P<name>[A-Z][A-Z0-9_]+)`?\b")


def _parse_event_names(bullets: list[str]) -> tuple[list[str], list[str]]:
    names: list[str] = []
    errors: list[str] = []
    for raw in bullets:
        m = _EVENT_NAME_RE.match(raw.strip())
        if m:
            names.append(m.group("name"))
        else:
            errors.append(f"unparsed event item: {raw}")
    return names, errors


_SYMBOL_RE = re.compile(r"`(?P<sym>[A-Za-z_][A-Za-z0-9_]*)`")
_ENTRY_POINT_RE = re.compile(
    r"`?(?P<group>taskforce\.[a-z_]+)`?\s*[:]{1,2}\s*`?(?P<name>[a-zA-Z0-9_-]+)`?"
)


def _parse_extension_points(bullets: list[str]) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    for raw in bullets:
        ep = _ENTRY_POINT_RE.search(raw)
        if ep:
            items.append(
                {
                    "kind": "entry_point",
                    "group": ep.group("group"),
                    "name": ep.group("name"),
                    "raw": raw,
                }
            )
            continue
        sym = _SYMBOL_RE.search(raw)
        if sym:
            items.append({"kind": "symbol", "name": sym.group("sym"), "raw": raw})
            continue
        errors.append(f"unparsed extension-point item: {raw}")
    return items, errors


_TEST_MARKER_RE = re.compile(r'spec\(\s*["\'](?P<marker>[^"\']+)["\']\s*\)')


def _parse_test_markers(bullets: list[str]) -> tuple[list[str], list[str]]:
    markers: list[str] = []
    errors: list[str] = []
    for raw in bullets:
        m = _TEST_MARKER_RE.search(raw)
        if m:
            markers.append(m.group("marker"))
        else:
            errors.append(f"unparsed test item: {raw}")
    return markers, errors


# ---------- Top-level ----------


def parse_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(text)
    sections = _split_sections(body)
    errors: list[str] = []

    def _bullets_of(name: str) -> list[str]:
        return _bullets(sections.get(name, ""))

    api_routes, e = _parse_api_routes(_bullets_of("api_surface"))
    errors.extend(e)

    config_keys, e = _parse_config_keys(_bullets_of("configuration_surface"))
    errors.extend(e)

    event_names, e = _parse_event_names(_bullets_of("event_stream_contract"))
    errors.extend(e)

    extension_points, e = _parse_extension_points(_bullets_of("extension_points"))
    errors.extend(e)

    test_markers, e = _parse_test_markers(_bullets_of("tests"))
    errors.extend(e)

    capabilities = _bullets_of("capabilities")
    invariants = _bullets_of("invariants")
    known_gaps = _bullets_of("known_gaps")
    cross_refs = _bullets_of("cross_references")

    # Frontmatter normalisation
    frontmatter = {k: v for k, v in frontmatter.items() if v}

    return {
        "feature": frontmatter.get("feature", path.stem),
        "spec_path": str(path),
        "frontmatter": frontmatter,
        "api_routes": api_routes,
        "config_keys": config_keys,
        "event_names": event_names,
        "extension_points": extension_points,
        "test_markers": test_markers,
        "capabilities": capabilities,
        "invariants": invariants,
        "known_gaps": known_gaps,
        "cross_refs": cross_refs,
        "parse_errors": errors,
        "section_names_found": sorted(sections.keys()),
    }


def main(argv: list[str]) -> int:
    # Force UTF-8 on stdout so we don't crash on Windows cp1252 default.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) != 2:
        print("usage: parse_spec.py <path/to/spec.md>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    result = parse_spec(path)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
