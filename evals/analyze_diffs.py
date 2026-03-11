"""Check git diff output and test results for each failed sample."""
import zipfile
import json

log = "logs/2026-03-10T17-32-47+00-00_swe-bench-verified-mini_nLx9GxxNKUytrnqgkHxBvy.eval"

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

        events = data.get("events", [])
        sandbox_events = [e for e in events if e.get("event") == "sandbox"]

        # Find git diff outputs and test results
        diff_output = ""
        test_results = []
        write_files = []
        for evt in sandbox_events:
            cmd = evt.get("cmd", "")
            output = evt.get("output", "")
            action = evt.get("action", "")
            result_code = evt.get("result", "")

            if "git diff" in cmd and action == "exec":
                diff_output = output[:500] if output else "(empty)"
            if "pytest" in cmd:
                # Get pass/fail from result code
                status = "PASS" if result_code == 0 else f"FAIL(rc={result_code})"
                test_results.append(f"{status}: {cmd[:100]}")
            if action == "write_file":
                path = evt.get("file", evt.get("path", "?"))
                write_files.append(str(path)[:80])

        marker = "PASS" if score_val else "FAIL"
        print(f"{'='*70}")
        print(f"{marker}: {sid}")
        print(f"  Write actions: {len(write_files)}")
        for wf in write_files[:3]:
            print(f"    -> {wf}")
        print(f"  Test results ({len(test_results)}):")
        for tr in test_results[:4]:
            print(f"    {tr}")
        print(f"  Git diff output:")
        if diff_output:
            for line in diff_output.split('\n')[:10]:
                print(f"    {line[:120]}")
        else:
            print("    (no git diff found)")
        print()
