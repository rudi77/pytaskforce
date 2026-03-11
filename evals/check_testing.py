"""Check if the agent ran pytest in each sample."""
import zipfile
import json
import re

log = "logs/2026-03-10T14-58-53+00-00_swe-bench-verified-mini_B6X8HREAvz3cr2zRD6E59o.eval"

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

        # Search through messages for shell tool calls containing pytest
        messages = data.get("messages", [])
        pytest_count = 0
        shell_commands = []
        for msg in messages:
            if isinstance(msg, dict):
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    if fn.get("name") == "shell":
                        args_str = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        except json.JSONDecodeError:
                            args = {"command": args_str}
                        cmd = args.get("command", "")
                        shell_commands.append(cmd)
                        if "pytest" in cmd or "python -m pytest" in cmd:
                            pytest_count += 1

        test_ran = "YES" if pytest_count > 0 else "NO"
        print(f"{sid}: score={score_val} pytest_calls={pytest_count} test_ran={test_ran} shell_cmds={len(shell_commands)}")
        if pytest_count > 0:
            for cmd in shell_commands:
                if "pytest" in cmd:
                    print(f"  -> {cmd[:120]}")
        print()
