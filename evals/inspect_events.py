"""Check events and output for pytest usage across all samples."""
import zipfile
import json

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

        # Search through events for tool calls
        events = data.get("events", [])
        shell_count = 0
        pytest_count = 0
        tool_names = []
        for evt in events:
            evt_type = evt.get("event", evt.get("type", ""))
            # Check for tool events
            if evt_type in ("tool", "tool_call"):
                tool_name = evt.get("name", evt.get("function", ""))
                tool_names.append(tool_name)
                # Check input for pytest
                inp = json.dumps(evt.get("input", evt.get("arguments", {})))
                if "pytest" in inp:
                    pytest_count += 1
                if tool_name == "shell":
                    shell_count += 1

        # Also search full JSON for pytest
        full_text = json.dumps(data)
        pytest_in_full = full_text.count("pytest")

        unique_tools = set(tool_names)
        print(f"{sid}: score={score_val} events={len(events)} pytest_in_json={pytest_in_full} unique_tools={unique_tools}")
