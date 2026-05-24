#!/usr/bin/env python3
"""Extract all registered FastAPI routes from a directory.

Walks every .py file under the given path, parses with the stdlib `ast`
module, finds `APIRouter(prefix=...)` declarations and the `@router.<method>`
decorators that hang off them, and emits a JSON list of:

    {"method": "POST", "path": "/api/v1/projects", "status_code": 201,
     "response_codes": [400, 409], "file": "src/.../projects.py", "line": 80}

The framework convention is that every router is mounted under `/api/v1`
when the FastAPI app is built (see `src/taskforce/api/server.py`). This
extractor prepends that prefix to every route, so the output paths match
what specs claim (e.g. `POST /api/v1/projects`).

Spec claims that don't include `/api/v1` (engine-only features) won't
match anything here — they shouldn't have api_routes claims to begin
with.

Stdlib only.

Usage:
    python check_routes.py src/taskforce/api/routes/
    python check_routes.py src/taskforce/api/routes/ > /tmp/routes.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

_API_PREFIX = "/api/v1"  # default; overridden per-router by server.py mount


def _extract_server_mounts(server_py: Path) -> dict[str, str]:
    """Parse server.py for `app.include_router(<module>.router, prefix=...)`.

    Returns {<router-module-stem>: <mount-prefix>}. Defaults to "" if no prefix=
    keyword is present.
    """
    mounts: dict[str, str] = {}
    if not server_py.exists():
        return mounts
    try:
        tree = ast.parse(server_py.read_text(encoding="utf-8"), filename=str(server_py))
    except SyntaxError:
        return mounts
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        # Expect <name>.router
        if not (isinstance(first, ast.Attribute) and isinstance(first.value, ast.Name)
                and first.attr == "router"):
            continue
        module = first.value.id  # e.g. "execution", "acp", "health"
        prefix = ""
        for kw in node.keywords:
            if kw.arg == "prefix":
                got = _string_value(kw.value)
                if got is not None:
                    prefix = got
        mounts[module] = prefix
    return mounts


def _string_value(node: ast.AST) -> str | None:
    """Return the string literal value of an AST node, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _int_value(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _extract_router_prefixes(tree: ast.AST) -> dict[str, str]:
    """Find `<name> = APIRouter(prefix=...)` assignments.

    Returns {variable_name: prefix_string}. Variables without an explicit
    prefix= kwarg get "".
    """
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Call) and _called_apirouter(node.value)):
            continue
        prefix = ""
        for kw in node.value.keywords:
            if kw.arg == "prefix":
                got = _string_value(kw.value)
                if got is not None:
                    prefix = got
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _called_apirouter(call: ast.Call) -> bool:
    """Heuristic: is this call `APIRouter(...)`?"""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "APIRouter":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "APIRouter":
        return True
    return False


def _extract_routes(
    tree: ast.AST,
    file_path: str,
    router_prefixes: dict[str, str],
) -> list[dict]:
    """Walk function defs, find @router.<method>(...) decorators."""
    routes: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            route = _extract_route_from_decorator(deco, router_prefixes)
            if route is not None:
                route["file"] = file_path
                route["line"] = node.lineno
                route["function"] = node.name
                routes.append(route)
    return routes


def _extract_route_from_decorator(
    deco: ast.AST,
    router_prefixes: dict[str, str],
) -> dict | None:
    """Recognise `@<router>.<method>("/path", ...)` and `@<router>.api_route(...)`."""
    if not isinstance(deco, ast.Call):
        return None
    func = deco.func
    if not isinstance(func, ast.Attribute):
        return None

    method_name = func.attr.lower()
    if method_name not in _HTTP_METHODS and method_name != "api_route":
        return None

    if not isinstance(func.value, ast.Name):
        return None
    router_name = func.value.id
    if router_name not in router_prefixes:
        return None

    # extract path (first positional or path=)
    path = None
    if deco.args:
        path = _string_value(deco.args[0])
    if path is None:
        for kw in deco.keywords:
            if kw.arg == "path":
                path = _string_value(kw.value)
                break
    if path is None:
        return None

    full_path = f"{_API_PREFIX}{router_prefixes[router_name]}{path}"
    full_path = full_path.rstrip("/")  # normalise trailing slash for matching
    if not full_path:
        full_path = "/"

    # status_code & responses
    status_code: int | None = None
    response_codes: list[int] = []
    methods: list[str] = []
    for kw in deco.keywords:
        if kw.arg == "status_code":
            v = _int_value(kw.value)
            if v is not None:
                status_code = v
        elif kw.arg == "responses" and isinstance(kw.value, ast.Dict):
            for key in kw.value.keys:
                v = _int_value(key)
                if v is not None:
                    response_codes.append(v)
        elif kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            for el in kw.value.elts:
                m = _string_value(el)
                if m:
                    methods.append(m.upper())

    if method_name == "api_route":
        if not methods:
            return None
    else:
        methods = [method_name.upper()]

    return {
        "methods": methods,
        "path": full_path,
        "status_code": status_code,
        "response_codes": sorted(set(response_codes)),
    }


def _scan_file(path: Path, mount_prefix: str) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [{"error": f"could not read {path}: {exc}"}]
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [{"error": f"syntax error in {path}: {exc}"}]

    prefixes = _extract_router_prefixes(tree)
    if not prefixes:
        return []
    # Inject the server mount as the global prefix used by the route assembler.
    # We adjust _extract_route_from_decorator's reliance on _API_PREFIX by
    # passing the mount prefix in via a wrapper: re-walk and emit per-route
    # with full_path = mount_prefix + router_prefix + path.
    routes: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            r = _extract_route_from_decorator(deco, prefixes)
            if r is None:
                continue
            # _extract_route_from_decorator already prepended _API_PREFIX;
            # strip it and replace with the real mount.
            stripped = r["path"]
            if stripped.startswith(_API_PREFIX):
                stripped = stripped[len(_API_PREFIX):]
            r["path"] = (mount_prefix + stripped).rstrip("/") or "/"
            r["file"] = str(path)
            r["line"] = node.lineno
            r["function"] = node.name
            routes.append(r)
    return routes


def scan(root: Path) -> list[dict]:
    """Walk all .py files under root and extract routes."""
    # Pull mount prefixes from server.py (if reachable from the routes dir)
    routes_dir = root if root.is_dir() else root.parent
    server_py = (routes_dir.parent / "server.py")
    mounts = _extract_server_mounts(server_py)

    all_routes: list[dict] = []
    files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
    for path in files:
        # Map filename stem → server mount prefix; default to /api/v1 if unknown.
        stem = path.stem
        mount = mounts.get(stem, _API_PREFIX) if mounts else _API_PREFIX
        for route in _scan_file(path, mount):
            if "error" in route:
                # Surface parse errors but don't crash
                continue
            # Expand multi-method routes into one entry per method
            for method in route["methods"]:
                all_routes.append(
                    {
                        "method": method,
                        "path": route["path"],
                        "status_code": route["status_code"],
                        "response_codes": route["response_codes"],
                        "file": route["file"],
                        "line": route["line"],
                        "function": route["function"],
                    }
                )
    return all_routes


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) != 2:
        print("usage: check_routes.py <path/to/routes/dir>", file=sys.stderr)
        return 2
    root = Path(argv[1])
    if not root.exists():
        print(f"path not found: {root}", file=sys.stderr)
        return 2
    routes = scan(root)
    json.dump(routes, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
