"""Compare two SWE-bench eval runs."""
import zipfile
import json
import sys

def get_scores(logfile):
    results = {}
    with zipfile.ZipFile(logfile) as z:
        names = sorted([n for n in z.namelist() if n.startswith("samples/")])
        for sf in names:
            data = json.loads(z.read(sf).decode())
            sid = data.get("id", "?")
            scores = data.get("scores", {})
            score_val = 0
            if isinstance(scores, dict):
                sv = scores.get("swe_bench_scorer", {})
                score_val = sv.get("value", 0) if isinstance(sv, dict) else sv
            meta = data.get("metadata", {})
            tools = meta.get("taskforce_tool_calls", 0)
            results[sid] = {"score": score_val, "tools": tools}
    return results

prev_log = "logs/2026-03-10T17-07-21+00-00_swe-bench-verified-mini_TSHfzaL5ULRtFxjbwPEjKr.eval"
curr_log = "logs/2026-03-10T19-07-56+00-00_swe-bench-verified-mini_HMjhfHSRxfFfkHKfQyVQAE.eval"

prev_r = get_scores(prev_log)
curr_r = get_scores(curr_log)

print(f"{'Sample':<32} {'Prev':>6} {'Curr':>6} {'PTools':>8} {'CTools':>8}")
print("-" * 64)
for sid in sorted(curr_r.keys()):
    ps = prev_r.get(sid, {}).get("score", "N/A")
    cs = curr_r[sid]["score"]
    pt = prev_r.get(sid, {}).get("tools", "N/A")
    ct = curr_r[sid]["tools"]
    marker = " <-- CHANGED" if ps != cs else ""
    print(f"{sid:<32} {ps:>6} {cs:>6} {pt:>8} {ct:>8}{marker}")

prev_total = sum(v["score"] for v in prev_r.values())
curr_total = sum(v["score"] for v in curr_r.values())
print(f"\nTotal: {prev_total}/{len(prev_r)} -> {curr_total}/{len(curr_r)}")
