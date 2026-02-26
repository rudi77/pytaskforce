"""Tests for tool_display_formatter — human-readable CLI tool output."""

from __future__ import annotations

import json

from taskforce.api.cli.tool_display_formatter import format_tool_call, format_tool_result

# ── Tool-Call formatting ────────────────────────────────────────────────


class TestFormatToolCall:
    """Tests for format_tool_call."""

    def test_file_read(self) -> None:
        result = format_tool_call("file_read", {"path": "/home/user/project/src/config.py"})
        assert "file_read" in result
        assert "config.py" in result

    def test_file_write_with_content_size(self) -> None:
        result = format_tool_call("file_write", {"path": "out.txt", "content": "x" * 1200})
        assert "file_write" in result
        assert "1,200" in result

    def test_edit(self) -> None:
        result = format_tool_call("edit", {"file_path": "/a/b/c/d/e.py"})
        assert "edit" in result
        assert "e.py" in result

    def test_shell_command(self) -> None:
        result = format_tool_call("shell", {"command": "ls -la /tmp"})
        assert "shell" in result
        assert "$ ls -la /tmp" in result

    def test_powershell_command(self) -> None:
        result = format_tool_call("powershell", {"command": "Get-Process"})
        assert "powershell" in result
        assert "$ Get-Process" in result

    def test_python_single_line(self) -> None:
        result = format_tool_call("python", {"code": "print('hello')"})
        assert "python" in result
        assert "print" in result
        assert "+0 lines" not in result

    def test_python_multiline(self) -> None:
        code = "import pandas\ndf = pandas.read_csv('data.csv')\nprint(df.head())"
        result = format_tool_call("python", {"code": code})
        assert "+2 lines" in result

    def test_web_search(self) -> None:
        result = format_tool_call("web_search", {"query": "python async tutorial"})
        assert "web_search" in result
        assert "python async" in result

    def test_web_fetch_strips_protocol(self) -> None:
        result = format_tool_call("web_fetch", {"url": "https://example.com/api/docs"})
        assert "web_fetch" in result
        assert "example.com/api/docs" in result
        assert "https://" not in result

    def test_git(self) -> None:
        result = format_tool_call("git", {"operation": "commit", "args": "-m 'fix bug'"})
        assert "git commit" in result

    def test_grep(self) -> None:
        result = format_tool_call("grep", {"pattern": "TODO", "path": "src/"})
        assert "grep" in result
        assert "/TODO/" in result

    def test_glob(self) -> None:
        result = format_tool_call("glob", {"pattern": "*.py", "path": "src/"})
        assert "glob" in result
        assert "*.py" in result

    def test_memory_list(self) -> None:
        result = format_tool_call("memory", {"action": "list"})
        assert result == "memory list"

    def test_memory_search_with_query(self) -> None:
        result = format_tool_call("memory", {"action": "search", "query": "Buchungsregel"})
        assert "memory search" in result
        assert "Buchungsregel" in result

    def test_send_notification(self) -> None:
        result = format_tool_call(
            "send_notification", {"channel": "telegram", "recipient_id": "user123"}
        )
        assert "telegram" in result
        assert "user123" in result

    def test_generic_with_invoice_data(self) -> None:
        params = {
            "invoice_data": {
                "invoice_number": "290",
                "supplier_name": "Musterbetrieb",
                "total": 1234.56,
            }
        }
        result = format_tool_call("check_compliance", params)
        assert "check_compliance" in result
        assert "#290" in result
        assert "Musterbetrieb" in result

    def test_generic_with_dict_param(self) -> None:
        params = {"config": {"a": 1, "b": 2, "c": 3}}
        result = format_tool_call("some_tool", params)
        assert "some_tool" in result
        assert "3 fields" in result

    def test_generic_with_list_param(self) -> None:
        params = {"items": [1, 2, 3, 4]}
        result = format_tool_call("some_tool", params)
        assert "4 items" in result

    def test_generic_with_short_string_param(self) -> None:
        result = format_tool_call("audit_log", {"action": "invoice_processed"})
        assert "audit_log" in result
        assert "action=invoice_processed" in result

    def test_generic_with_long_string_param(self) -> None:
        params = {"data": "x" * 100}
        result = format_tool_call("some_tool", params)
        assert "100 chars" in result

    def test_generic_empty_params(self) -> None:
        result = format_tool_call("my_tool", {})
        assert result == "my_tool"

    def test_generic_limits_to_3_params(self) -> None:
        params = {"a": "1", "b": "2", "c": "3", "d": "4"}
        result = format_tool_call("big_tool", params)
        # Should not include the 4th param key
        assert "d=" not in result

    def test_handles_non_dict_gracefully(self) -> None:
        # Even if called with wrong type, should not crash
        result = format_tool_call("oops", {})
        assert "oops" in result


# ── Tool-Result formatting ──────────────────────────────────────────────


class TestFormatToolResult:
    """Tests for format_tool_result."""

    def test_error_result(self) -> None:
        output = json.dumps({"error": "File not found"})
        result = format_tool_result("file_read", False, output)
        assert "File not found" in result

    def test_error_result_plain_text(self) -> None:
        result = format_tool_result("shell", False, "command not found")
        assert "command not found" in result

    def test_file_read(self) -> None:
        output = json.dumps({"content": "x" * 500, "path": "/a/b/config.py"})
        result = format_tool_result("file_read", True, output)
        assert "500" in result
        assert "config.py" in result

    def test_file_write(self) -> None:
        output = json.dumps({"path": "/project/out.txt", "success": True})
        result = format_tool_result("file_write", True, output)
        assert "Wrote" in result
        assert "out.txt" in result

    def test_edit_with_replacements(self) -> None:
        output = json.dumps({"path": "/a/b/c.py", "replacements": 2})
        result = format_tool_result("edit", True, output)
        assert "Edited" in result
        assert "2 replacements" in result

    def test_shell_single_line(self) -> None:
        output = json.dumps({"stdout": "total 48"})
        result = format_tool_result("shell", True, output)
        assert "total 48" in result

    def test_shell_multiline(self) -> None:
        output = json.dumps({"stdout": "total 48\ndrwxr-xr-x 2\n-rw-r--r-- 1\nfoo\nbar"})
        result = format_tool_result("shell", True, output)
        assert "total 48" in result
        assert "+4 lines" in result

    def test_shell_no_output(self) -> None:
        output = json.dumps({"stdout": ""})
        result = format_tool_result("shell", True, output)
        assert "(no output)" in result

    def test_python_result(self) -> None:
        output = json.dumps({"result": 42})
        result = format_tool_result("python", True, output)
        assert "result = 42" in result

    def test_python_stdout_fallback(self) -> None:
        output = json.dumps({"stdout": "hello world"})
        result = format_tool_result("python", True, output)
        assert "hello world" in result

    def test_web_search(self) -> None:
        output = json.dumps({"results": [1, 2, 3], "query": "python async"})
        result = format_tool_result("web_search", True, output)
        assert "3 results" in result
        assert "python async" in result

    def test_web_fetch(self) -> None:
        output = json.dumps(
            {"status_code": 200, "url": "https://example.com/api", "content": "x" * 3200}
        )
        result = format_tool_result("web_fetch", True, output)
        assert "HTTP 200" in result
        assert "example.com" in result

    def test_git(self) -> None:
        output = json.dumps({"output": "3 files changed\n5 insertions"})
        result = format_tool_result("git", True, output)
        assert "3 files changed" in result
        assert "+1 lines" in result

    def test_grep(self) -> None:
        output = json.dumps({"matches": ["a", "b", "c"], "files": ["x.py", "y.py"]})
        result = format_tool_result("grep", True, output)
        assert "3 matches" in result
        assert "2 files" in result

    def test_glob(self) -> None:
        output = json.dumps({"files": ["a.py", "b.py"], "pattern": "*.py"})
        result = format_tool_result("glob", True, output)
        assert "2 files" in result
        assert "*.py" in result

    def test_memory_records(self) -> None:
        output = json.dumps({"records": [{"id": "abc123"}]})
        result = format_tool_result("memory", True, output)
        assert result == "1 record"

    def test_memory_no_records(self) -> None:
        output = json.dumps({"records": []})
        result = format_tool_result("memory", True, output)
        assert "No records" in result

    def test_memory_id(self) -> None:
        output = json.dumps({"id": "d52e28ef1e19469797f7730f2edca447"})
        result = format_tool_result("memory", True, output)
        assert "[d52e28ef]" in result

    def test_send_notification(self) -> None:
        output = json.dumps({"channel": "telegram", "recipient_id": "user1"})
        result = format_tool_result("send_notification", True, output)
        assert "Sent via telegram" in result

    def test_generic_compliant(self) -> None:
        output = json.dumps({"success": True, "is_compliant": True})
        result = format_tool_result("check_compliance", True, output)
        assert result == "Compliant"

    def test_generic_non_compliant(self) -> None:
        output = json.dumps({"success": True, "is_compliant": False})
        result = format_tool_result("check_compliance", True, output)
        assert result == "Non-compliant"

    def test_generic_confidence_and_recommendation(self) -> None:
        output = json.dumps({"overall_confidence": 0.994, "recommendation": "auto_book"})
        result = format_tool_result("confidence_evaluator", True, output)
        assert "99.4%" in result
        assert "auto_book" in result

    def test_generic_rule_matches(self) -> None:
        output = json.dumps({"rule_matches": [{"id": 1}, {"id": 2}, {"id": 3}]})
        result = format_tool_result("semantic_rule_engine", True, output)
        assert "3 rules matched" in result

    def test_generic_result_key(self) -> None:
        output = json.dumps({"result": "All good"})
        result = format_tool_result("custom_tool", True, output)
        assert "All good" in result

    def test_generic_field_count_fallback(self) -> None:
        output = json.dumps({"foo": 1, "bar": 2, "baz": 3})
        result = format_tool_result("unknown_tool", True, output)
        assert "3 fields" in result

    def test_plain_text_output(self) -> None:
        result = format_tool_result("some_tool", True, "plain text output here")
        assert "plain text output" in result

    def test_truncation_of_long_output(self) -> None:
        result = format_tool_result("some_tool", True, "x" * 200)
        assert len(result) <= 83  # 80 chars + "..."
