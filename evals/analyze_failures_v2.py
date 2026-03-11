"""Analyze failures from the final SWE-bench Mini run."""
import zipfile
import json
import re

log = "logs/2026-03-10T17-07-21+00-00_swe-bench-verified-mini_TSHfzaL5ULRtFxjbwPEjKr.eval"

with zipfile.ZipFile(log) as z:
    names = sorted([n for n in z.namelist() if n.startswith("samples/")])
    for sf in names:
        data = json.loads(z.read(sf).decode())
        sid = data.get("id", "?")
        scores = data.get("scores", {})
        score_val = 0
        if isinstance(scores, dict):
            sv = scores.get("swe_bench_scorer", {})
            score_val = sv.get("value", 0) if isinstance(sv, dict) else sv

        if score_val == 1.0:
            continue  # Skip passes

        full = json.dumps(data)

        # Extract issue text from input
        inp = data.get("input", "")
        if isinstance(inp, list):
            inp = inp[0].get("content", "") if inp else ""
        elif isinstance(inp, dict):
            inp = inp.get("content", inp.get("text", ""))
        issue_text = str(inp)[:300]

        # Extract metadata
        meta = data.get("metadata", {})
        repo = meta.get("repo", "?")
        patch = meta.get("patch", "")
        fail_to_pass = meta.get("FAIL_TO_PASS", "")
        test_patch = meta.get("test_patch", "")[:200] if meta.get("test_patch") else ""

        # Count tool usage
        pytest_cmds = re.findall(r'python -m pytest[^"\\]*', full)
        git_checkouts = full.count("git checkout")
        git_diffs = full.count("git diff")
        edit_count = full.count('"name": "edit"') + full.count('"name":"edit"')

        # Extract shell commands
        shell_cmds = re.findall(r'"command":\s*"([^"]{1,200})"', full)
        pytest_shell = [c for c in shell_cmds if "pytest" in c]

        # Look for error patterns
        content_policy = full.count("ContentPolicyViolation")

        # Get the completion/output
        output = data.get("output", {})
        completion = ""
        if isinstance(output, dict):
            completion = (output.get("completion") or "")[:300]

        # Try to find what the agent's patch looks like via sandbox events
        # Look for edit tool calls and their content
        edit_calls = re.findall(r'"old_string":\s*"([^"]{1,100})"', full)

        print(f"{'='*70}")
        print(f"FAILED: {sid}")
        print(f"Repo: {repo}")
        print(f"Issue: {issue_text[:200]}...")
        print(f"Expected failing test: {fail_to_pass[:150]}")
        print(f"Edits: {edit_count}, pytest runs: {len(pytest_cmds)}, git checkouts: {git_checkouts}, content_policy_errors: {content_policy}")
        if pytest_shell:
            print(f"Pytest commands:")
            for cmd in pytest_shell[:3]:
                print(f"  $ {cmd}")
        if edit_calls:
            print(f"Edit targets (old_string snippets):")
            for ec in edit_calls[:3]:
                print(f"  - {ec[:80]}")
        print(f"Agent output: {completion[:200]}")
        print()
