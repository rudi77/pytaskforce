"""Human-readable formatting for tool calls and results in CLI output.

Transforms raw tool parameters and JSON result strings into concise,
scannable one-liners for the interactive chat display.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

_ToolCallFormatter = Callable[[str, dict[str, Any]], str]
_ToolResultFormatter = Callable[[str, Any], str]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_tool_call(tool_name: str, params: dict[str, Any]) -> str:
    """Format a tool call as a readable one-liner.

    Args:
        tool_name: Short tool name (e.g. ``file_read``, ``shell``).
        params: Tool parameters dict.

    Returns:
        Human-readable summary string (without leading emoji).
    """
    formatter = _TOOL_CALL_FORMATTERS.get(tool_name, _call_generic)
    try:
        return formatter(tool_name, params)
    except Exception:
        return _call_generic(tool_name, params)


def format_tool_result(tool_name: str, success: bool, output: str) -> str:
    """Format a tool result as a readable summary.

    Args:
        tool_name: Short tool name.
        success: Whether the tool execution succeeded.
        output: Raw output string (often JSON).

    Returns:
        Human-readable summary string.
    """
    if not success:
        return _format_error(output)

    data = _try_parse_output(output)
    formatter = _TOOL_RESULT_FORMATTERS.get(tool_name, _result_generic)
    try:
        return formatter(tool_name, data if data is not None else output)
    except Exception:
        return _truncate(str(output))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shorten_path(path: str, max_parts: int = 3) -> str:
    """Shorten a file path to the last *max_parts* segments."""
    parts = path.replace("\\", "/").rstrip("/").split("/")
    if len(parts) <= max_parts:
        return path
    return ".../" + "/".join(parts[-max_parts:])


def _truncate(text: str, max_len: int = 80) -> str:
    """Truncate *text* to *max_len* characters, adding ``...`` if needed."""
    text = text.strip().replace("\n", " ").replace("\r", "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _strip_protocol(url: str) -> str:
    """Remove ``http(s)://`` prefix from a URL for display."""
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            return url[len(prefix) :]
    return url


def _try_parse_output(output: str) -> dict[str, Any] | list[Any] | None:
    """Attempt to parse *output* as JSON. Return ``None`` on failure."""
    if not isinstance(output, str):
        return None
    text = output.strip()
    if not text or text[0] not in ("{", "["):
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _format_error(output: str) -> str:
    """Format an error result."""
    data = _try_parse_output(output)
    if isinstance(data, dict):
        msg = data.get("error") or data.get("message") or data.get("detail", "")
        if msg:
            return _truncate(str(msg))
    return _truncate(str(output))


def _summarize_param(key: str, value: Any) -> str:
    """Produce a short summary of a single parameter value."""
    if isinstance(value, dict):
        # Detect invoice_data-style dicts
        inv_nr = value.get("invoice_number") or value.get("number")
        supplier = value.get("supplier_name") or value.get("supplier")
        if inv_nr or supplier:
            parts = []
            if inv_nr:
                parts.append(f"#{inv_nr}")
            if supplier:
                parts.append(str(supplier))
            return f"{key} ({', '.join(parts)})"
        return f"{key} ({len(value)} fields)"
    if isinstance(value, list):
        return f"{key} ({len(value)} items)"
    text = str(value)
    if len(text) > 60:
        return f"{key} ({len(text)} chars)"
    return f"{key}={_truncate(text, 60)}"


def _count_lines(text: str) -> int:
    """Count non-empty lines in *text*."""
    return len([ln for ln in text.splitlines() if ln.strip()])


# ---------------------------------------------------------------------------
# Tool-Call Formatters
# ---------------------------------------------------------------------------


def _call_file_read(_name: str, params: dict[str, Any]) -> str:
    path = params.get("path") or params.get("file_path", "")
    return f"file_read {_shorten_path(str(path))}"


def _call_file_write(_name: str, params: dict[str, Any]) -> str:
    path = params.get("path") or params.get("file_path", "")
    content = params.get("content", "")
    size = len(str(content))
    return f"file_write {_shorten_path(str(path))} ({size:,} chars)"


def _call_edit(_name: str, params: dict[str, Any]) -> str:
    path = params.get("path") or params.get("file_path", "")
    return f"edit {_shorten_path(str(path))}"


def _call_shell(name: str, params: dict[str, Any]) -> str:
    cmd = params.get("command", "")
    return f"{name} $ {_truncate(str(cmd), 70)}"


def _call_python(_name: str, params: dict[str, Any]) -> str:
    code = str(params.get("code", ""))
    first_line = code.strip().split("\n", 1)[0]
    line_count = _count_lines(code)
    suffix = f" (+{line_count - 1} lines)" if line_count > 1 else ""
    return f"python {_truncate(first_line, 60)}{suffix}"


def _call_web_search(_name: str, params: dict[str, Any]) -> str:
    query = params.get("query", "")
    return f"web_search '{_truncate(str(query), 60)}'"


def _call_web_fetch(_name: str, params: dict[str, Any]) -> str:
    url = _strip_protocol(str(params.get("url", "")))
    return f"web_fetch {_truncate(url, 70)}"


def _call_git(_name: str, params: dict[str, Any]) -> str:
    operation = params.get("operation") or params.get("command", "")
    args = params.get("args", "")
    text = f"git {operation}"
    if args:
        text += f" {_truncate(str(args), 60)}"
    return text


def _call_grep(_name: str, params: dict[str, Any]) -> str:
    pattern = params.get("pattern", "")
    path = params.get("path", ".")
    return f"grep /{pattern}/ in {_shorten_path(str(path))}"


def _call_glob(_name: str, params: dict[str, Any]) -> str:
    pattern = params.get("pattern", "")
    path = params.get("path", ".")
    return f"glob {pattern} in {_shorten_path(str(path))}"


def _call_memory(_name: str, params: dict[str, Any]) -> str:
    action = params.get("action", "")
    query = params.get("query", "")
    text = f"memory {action}"
    if query:
        text += f" '{_truncate(str(query), 50)}'"
    return text


def _call_send_notification(_name: str, params: dict[str, Any]) -> str:
    channel = params.get("channel", "")
    recipient = params.get("recipient_id") or params.get("recipient", "")
    return f"send_notification -> {channel}:{recipient}"


def _call_generic(tool_name: str, params: dict[str, Any]) -> str:
    """Fallback formatter for unknown / MCP / custom tools."""
    if not params:
        return tool_name

    parts: list[str] = []
    for key, value in list(params.items())[:3]:
        parts.append(_summarize_param(key, value))

    return f"{tool_name} {', '.join(parts)}"


_TOOL_CALL_FORMATTERS: dict[str, _ToolCallFormatter] = {
    "file_read": _call_file_read,
    "file_write": _call_file_write,
    "edit": _call_edit,
    "shell": _call_shell,
    "powershell": _call_shell,
    "python": _call_python,
    "web_search": _call_web_search,
    "web_fetch": _call_web_fetch,
    "git": _call_git,
    "grep": _call_grep,
    "glob": _call_glob,
    "memory": _call_memory,
    "send_notification": _call_send_notification,
}


# ---------------------------------------------------------------------------
# Tool-Result Formatters
# ---------------------------------------------------------------------------


def _result_file_read(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        content = data.get("content", "")
        path = data.get("path") or data.get("file_path", "")
        size = len(str(content))
        if path:
            return f"{size:,} chars from {_shorten_path(str(path))}"
        return f"{size:,} chars"
    return _truncate(str(data))


def _result_file_write(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        path = data.get("path") or data.get("file_path", "")
        if path:
            return f"Wrote {_shorten_path(str(path))}"
    return "Written"


def _result_edit(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        path = data.get("path") or data.get("file_path", "")
        replacements = data.get("replacements") or data.get("changes", 0)
        parts = []
        if path:
            parts.append(f"Edited {_shorten_path(str(path))}")
        else:
            parts.append("Edited")
        if replacements:
            parts.append(f"({replacements} replacements)")
        return " ".join(parts)
    return "Edited"


def _result_shell(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        stdout = str(data.get("stdout") or data.get("output", ""))
    else:
        stdout = str(data)
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    if not lines:
        return "(no output)"
    first = _truncate(lines[0], 70)
    if len(lines) > 1:
        return f"{first} (+{len(lines) - 1} lines)"
    return first


def _result_python(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        result = data.get("result")
        if result is not None:
            return f"result = {_truncate(str(result), 70)}"
        stdout = data.get("stdout") or data.get("output", "")
        if stdout:
            return _result_shell(_name, {"stdout": stdout})
    return _truncate(str(data))


def _result_web_search(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        results = data.get("results", [])
        query = data.get("query", "")
        count = len(results) if isinstance(results, list) else 0
        text = f"{count} results"
        if query:
            text += f" for '{_truncate(str(query), 40)}'"
        return text
    return _truncate(str(data))


def _result_web_fetch(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        status = data.get("status_code") or data.get("status", "")
        url = data.get("url", "")
        content = str(data.get("content") or data.get("body", ""))
        parts = []
        if status:
            parts.append(f"HTTP {status}")
        if url:
            parts.append(_truncate(_strip_protocol(str(url)), 40))
        if content:
            parts.append(f"({len(content):,} chars)")
        return " ".join(parts) if parts else "Fetched"
    return _truncate(str(data))


def _result_git(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        output = str(data.get("output") or data.get("stdout", ""))
    else:
        output = str(data)
    lines = [ln for ln in output.strip().splitlines() if ln.strip()]
    if not lines:
        return "Done"
    first = _truncate(lines[0], 70)
    if len(lines) > 1:
        return f"{first} (+{len(lines) - 1} lines)"
    return first


def _result_grep(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        matches = data.get("matches", [])
        files = data.get("files", [])
        if isinstance(matches, list) and isinstance(files, list):
            return f"{len(matches)} matches in {len(files)} files"
        if isinstance(matches, list):
            return f"{len(matches)} matches"
        match_count = data.get("match_count") or data.get("count", 0)
        if match_count:
            return f"{match_count} matches"
    return _truncate(str(data))


def _result_glob(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        files = data.get("files", data.get("matches", []))
        pattern = data.get("pattern", "")
        if isinstance(files, list):
            text = f"{len(files)} files"
            if pattern:
                text += f" matching {pattern}"
            return text
    return _truncate(str(data))


def _result_memory(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        if "records" in data:
            records = data["records"]
            if isinstance(records, list):
                if not records:
                    return "No records"
                n = len(records)
                return f"{n} record{'s' if n != 1 else ''}"
        record_id = data.get("id") or data.get("record_id", "")
        if record_id:
            return f"[{str(record_id)[:8]}]"
        message = data.get("message", "")
        if message:
            return _truncate(str(message))
    return _truncate(str(data))


def _result_send_notification(_name: str, data: Any) -> str:
    if isinstance(data, dict):
        channel = data.get("channel", "")
        recipient = data.get("recipient_id") or data.get("recipient", "")
        if channel:
            return f"Sent via {channel}" + (f" to {recipient}" if recipient else "")
    return "Sent"


def _result_generic(_name: str, data: Any) -> str:
    """Fallback formatter: look for common keys in parsed JSON."""
    if not isinstance(data, dict):
        return _truncate(str(data))

    # Compliance results
    is_compliant = data.get("is_compliant")
    if is_compliant is not None:
        return "Compliant" if is_compliant else "Non-compliant"

    # Confidence / recommendation
    confidence = data.get("overall_confidence") or data.get("confidence")
    recommendation = data.get("recommendation")
    if confidence is not None and recommendation:
        pct = f"{float(confidence) * 100:.1f}%" if float(confidence) <= 1 else f"{confidence}%"
        return f"{pct} -> {recommendation}"
    if recommendation:
        return _truncate(str(recommendation))

    # Rule matches
    rule_matches = data.get("rule_matches")
    if isinstance(rule_matches, list):
        return f"{len(rule_matches)} rules matched"

    # Common result keys
    for key in ("result", "output", "message", "summary", "text"):
        val = data.get(key)
        if val is not None and str(val).strip():
            return _truncate(str(val))

    # Last resort: field count
    return f"Result with {len(data)} fields"


_TOOL_RESULT_FORMATTERS: dict[str, _ToolResultFormatter] = {
    "file_read": _result_file_read,
    "file_write": _result_file_write,
    "edit": _result_edit,
    "shell": _result_shell,
    "powershell": _result_shell,
    "python": _result_python,
    "web_search": _result_web_search,
    "web_fetch": _result_web_fetch,
    "git": _result_git,
    "grep": _result_grep,
    "glob": _result_glob,
    "memory": _result_memory,
    "send_notification": _result_send_notification,
}
