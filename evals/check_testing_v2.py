"""Check pytest execution across all samples via sandbox events."""
import zipfile
import json
import re

log = "logs/2026-03-10T17-07-21+00-00_swe-bench-verified-mini_TSHfzaL5ULRtFxjbwPEjKr.eval"

with zipfile.ZipFile(log) as z:
    names = sorted([n for n in z.namelist() if n.startswith("samples/")])
    total_testing = 0
    for sf in names:
        data = json.loads(z.read(sf).decode())
        sid = data.get("id", "?")
        scores = data.get("scores", {})
        score_val = 0
        if isinstance(scores, dict):
            sv = scores.get("swe_bench_scorer", {})
            score_val = sv.get("value", 0) if isinstance(sv, dict) else sv

        full = json.dumps(data)
        pytest_cmds = re.findall(r'python -m pytest[^"\\]*', full)
        git_diff = full.count("git diff")
        git_checkout = full.count("git checkout")
        tested = "YES" if len(pytest_cmds) > 0 else "NO"
        if len(pytest_cmds) > 0:
            total_testing += 1
        print(f"{sid}: score={score_val} tested={tested} pytest_runs={len(pytest_cmds)} git_diff={git_diff} git_checkout={git_checkout}")

    print(f"\nTotal samples that ran tests: {total_testing}/20")
