#!/usr/bin/env python3
"""Run deterministic spec checks (routes, configs, enums, extension points).

Emits one JSON object per feature with per-claim PASS/FAIL/WARN verdicts.
Handles the actual JSON shape emitted by parse_spec.py (dicts with `kind`).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
REPO = ROOT  # /home/user/pytaskforce

CONFIG_FILES: list[Path] = []
for cdir in [
    REPO / "src" / "taskforce" / "configs",
    *list((REPO / "agents").glob("*/configs")),
]:
    if cdir.exists():
        for ext in (".yaml", ".yml"):
            CONFIG_FILES.extend(cdir.rglob(f"*{ext}"))

REGISTERED_ROUTES = json.loads(Path("/tmp/registered_routes.json").read_text())
EVENT_ENUMS = json.loads(Path("/tmp/event_enums.json").read_text())

ROUTE_LOOKUP: dict[tuple[str, str], dict] = {}
for r in REGISTERED_ROUTES:
    method = r.get("method", "").upper()
    path = r.get("path", "")
    ROUTE_LOOKUP[(method, path)] = r


def _normalize_path(p: str) -> str:
    p = p.strip()
    if not p.startswith("/"):
        p = "/" + p
    if p.endswith("/") and p != "/":
        p = p[:-1]
    return p


def _find_route(method: str, path: str) -> tuple[str, str]:
    method = method.upper()
    np = _normalize_path(path)
    if (method, np) in ROUTE_LOOKUP:
        loc = ROUTE_LOOKUP[(method, np)]
        return "PASS", f"{loc.get('file','?')}:{loc.get('line','?')}"
    spec_pattern = re.sub(r"\{[^}]+\}", "{X}", np)
    for (m, p), rec in ROUTE_LOOKUP.items():
        if m != method:
            continue
        if re.sub(r"\{[^}]+\}", "{X}", p) == spec_pattern:
            return "WARN", f"param-name-mismatch: spec={np} code={p} ({rec.get('file','?')}:{rec.get('line','?')})"
    return "FAIL", f"no route registered for {method} {np}"


def _load_yaml(path: Path) -> Any:
    import yaml
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _walk(d: Any, parts: list[str]) -> Any:
    for k in parts:
        if isinstance(d, dict):
            d = d.get(k)
        elif isinstance(d, list):
            return None
        else:
            return None
        if d is None:
            return None
    return d


def _check_config_key(dotted: str, expected_default: str | None) -> tuple[str, str]:
    """Check whether a dotted profile key exists anywhere across known YAMLs.

    The spec doesn't tag keys with a profile; we scan all framework + agent
    profiles. Pass if any profile defines the key; FAIL otherwise.
    """
    parts = dotted.split(".")
    hits: list[tuple[str, Any]] = []
    for cfile in CONFIG_FILES:
        data = _load_yaml(cfile)
        if data is None:
            continue
        v = _walk(data, parts)
        if v is not None:
            hits.append((str(cfile.relative_to(REPO)), v))
    if not hits:
        return "FAIL", f"key {dotted} not defined in any profile YAML"
    if expected_default:
        # check first hit
        actual = str(hits[0][1])
        if actual == expected_default or actual.lower() == expected_default.lower():
            return "PASS", f"{hits[0][0]}: {dotted} = {hits[0][1]}"
        return "WARN", f"{hits[0][0]}: {dotted} = {hits[0][1]} (spec claims default '{expected_default}')"
    sample = hits[0]
    return "PASS", f"{sample[0]}: {dotted} = {sample[1]} (in {len(hits)} profile{'s' if len(hits)>1 else ''})"


def _check_env_var(name: str) -> tuple[str, str]:
    """Grep for env var usage in code (os.environ / getenv / Settings classes)."""
    try:
        res = subprocess.run(
            ["grep", "-rEn", re.escape(name), str(REPO / "src"), "--include=*.py"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
        lines = [ln for ln in res.stdout.splitlines() if name in ln]
        if not lines:
            # also check agents/
            res2 = subprocess.run(
                ["grep", "-rEn", re.escape(name), str(REPO / "agents"), "--include=*.py"],
                capture_output=True, text=True, errors="replace", timeout=20,
            )
            lines = [ln for ln in res2.stdout.splitlines() if name in ln]
        if not lines:
            return "FAIL", f"env var {name} not referenced in code"
        first = lines[0].replace(str(REPO) + "/", "")
        more = f" (+{len(lines)-1})" if len(lines) > 1 else ""
        return "PASS", f"{first}{more}"
    except Exception as e:
        return "WARN", f"grep failed: {e}"


def _check_event(name: str) -> tuple[str, str]:
    for enum_name, members in EVENT_ENUMS.items():
        if name in members:
            return "PASS", f"{enum_name}.{name}"
        if name.lower() in [m.lower() for m in members]:
            return "WARN", f"{enum_name}.{name} (case-insensitive match)"
    return "FAIL", f"event '{name}' not in any enum"


def _grep_symbol(symbol: str) -> tuple[str, str]:
    pattern = rf"^(async def |def |class ){re.escape(symbol)}\b"
    targets = [REPO / "src" / "taskforce", REPO / "agents", REPO / "cli" / "src", REPO / "packages"]
    found: list[str] = []
    for t in targets:
        if not t.exists():
            continue
        try:
            res = subprocess.run(
                ["grep", "-rEn", pattern, str(t), "--include=*.py"],
                capture_output=True, text=True, errors="replace", timeout=20,
            )
            for ln in res.stdout.splitlines():
                found.append(ln)
        except Exception:
            pass
    if not found:
        # try as bare module-level assignment
        try:
            res = subprocess.run(
                ["grep", "-rEn", rf"^{re.escape(symbol)}\s*=", str(REPO / "src" / "taskforce"), "--include=*.py"],
                capture_output=True, text=True, errors="replace", timeout=20,
            )
            for ln in res.stdout.splitlines():
                found.append(ln + " [assignment]")
        except Exception:
            pass
    if not found:
        return "FAIL", f"symbol '{symbol}' not found in src/, agents/, cli/, packages/"
    rel = found[0].replace(str(REPO) + "/", "")
    return ("PASS", f"{rel} (+{len(found)-1} more)") if len(found) > 1 else ("PASS", rel)


def _check_entry_point(group: str, name: str) -> tuple[str, str]:
    """Check entry-point declaration in any pyproject.toml."""
    try:
        res = subprocess.run(
            ["grep", "-rEln", re.escape(f"[project.entry-points.\"{group}\"]"), str(REPO),
             "--include=pyproject.toml"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
        files = [ln for ln in res.stdout.splitlines() if ln]
        for f in files:
            txt = Path(f).read_text()
            # find the group section and check if `name = ` appears
            grp_idx = txt.find(f'[project.entry-points."{group}"]')
            if grp_idx < 0:
                continue
            # search for next [ section or EOF
            tail = txt[grp_idx:]
            nxt = re.search(r"^\[", tail[1:], re.MULTILINE)
            block = tail[:nxt.start() + 1] if nxt else tail
            if re.search(rf"^{re.escape(name)}\s*=", block, re.MULTILINE):
                rel = f.replace(str(REPO) + "/", "")
                return "PASS", f"{rel}: {group}.{name}"
        return "FAIL", f"entry-point {group}.{name} not declared in any pyproject.toml"
    except Exception as e:
        return "WARN", f"entry-point check failed: {e}"


def check_spec(spec_path: Path) -> dict:
    data = json.loads(spec_path.read_text())
    feature = data["feature"]
    fm = data.get("frontmatter", {})
    out: dict = {
        "feature": feature,
        "status": fm.get("status", "?"),
        "last_verified": fm.get("last_verified", ""),
        "mech": {
            "routes": [],
            "configs": [],
            "events": [],
            "extension_points": [],
        },
        "counts": {},
        "parse_errors": data.get("parse_errors", []),
    }

    for route in data.get("api_routes", []):
        if route.get("kind") != "route":
            continue
        method = route.get("method", "")
        path = route.get("path", "")
        if not method or not path:
            continue
        v, ev = _find_route(method, path)
        out["mech"]["routes"].append({
            "method": method, "path": path,
            "status_claim": route.get("status"),
            "condition": route.get("condition", ""),
            "verdict": v, "evidence": ev,
        })

    for ck in data.get("config_keys", []):
        if not isinstance(ck, dict):
            continue
        kind = ck.get("kind")
        if kind == "env_var":
            name = ck.get("name", "")
            if not name:
                continue
            v, ev = _check_env_var(name)
            out["mech"]["configs"].append({
                "kind": "env_var", "name": name,
                "verdict": v, "evidence": ev,
            })
        elif kind == "profile_key":
            key = ck.get("key", "")
            default = ck.get("default")
            if not key or not re.match(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$", key, re.IGNORECASE):
                # skip mis-parsed entries (single tokens like "false", "true")
                continue
            v, ev = _check_config_key(key, default)
            out["mech"]["configs"].append({
                "kind": "profile_key", "key": key, "default": default,
                "verdict": v, "evidence": ev,
            })

    for ev_name in data.get("event_names", []):
        if not isinstance(ev_name, str) or not ev_name:
            continue
        v, ev = _check_event(ev_name)
        out["mech"]["events"].append({
            "name": ev_name, "verdict": v, "evidence": ev,
        })

    for sym in data.get("extension_points", []):
        if not isinstance(sym, dict):
            continue
        kind = sym.get("kind")
        if kind == "entry_point":
            v, ev = _check_entry_point(sym.get("group", ""), sym.get("name", ""))
            out["mech"]["extension_points"].append({
                "kind": "entry_point", "group": sym.get("group"), "name": sym.get("name"),
                "verdict": v, "evidence": ev,
            })
        elif kind == "symbol":
            name = sym.get("name", "")
            if not name:
                continue
            v, ev = _grep_symbol(name)
            out["mech"]["extension_points"].append({
                "kind": "symbol", "name": name,
                "verdict": v, "evidence": ev,
            })

    for k, arr in out["mech"].items():
        pass_n = sum(1 for x in arr if x["verdict"] == "PASS")
        fail_n = sum(1 for x in arr if x["verdict"] == "FAIL")
        warn_n = sum(1 for x in arr if x["verdict"] == "WARN")
        out["counts"][k] = {"pass": pass_n, "fail": fail_n, "warn": warn_n, "total": len(arr)}

    return out


def main():
    spec_files = sorted(Path("/tmp").glob("spec_*.json"))
    results = {}
    for sf in spec_files:
        name = sf.stem.replace("spec_", "")
        try:
            results[name] = check_spec(sf)
        except Exception as e:
            import traceback
            results[name] = {"feature": name, "error": f"{e}\n{traceback.format_exc()[-500:]}"}
    out_file = Path("/tmp/mech_results.json")
    out_file.write_text(json.dumps(results, indent=2))
    print(f"Wrote {out_file} ({len(results)} features)")
    for name, res in results.items():
        if "error" in res:
            print(f"  ERR  {name}: {res['error'][:80]}")
            continue
        c = res["counts"]
        tot_fail = sum(c[k]["fail"] for k in c)
        tot_warn = sum(c[k]["warn"] for k in c)
        tot = sum(c[k]["total"] for k in c)
        marker = "OK  " if tot_fail == 0 and tot_warn == 0 else ("WARN" if tot_fail == 0 else "FAIL")
        print(f"  {marker} {name}: {tot} claims, {tot_fail} fail, {tot_warn} warn")


if __name__ == "__main__":
    main()
