"""Check what tools the agent actually called in each sample."""
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

        full = json.dumps(data)

        # Count ALL tool-like invocations
        tool_counts = {}
        # Look for tool names in various formats
        for tool in ["shell", "file_read", "file_write", "edit", "grep", "glob", "git"]:
            # Count in sandbox events content
            count = len(re.findall(rf'"name":\s*"{tool}"', full))
            # Also check for tool calls in text
            count2 = len(re.findall(rf'tool[_\s]*(?:call|execute)[^{{]*{tool}', full, re.IGNORECASE))
            tool_counts[tool] = max(count, count2)

        # Check for file modifications via shell (sed, echo >>, tee, etc.)
        sed_count = full.count("sed -i") + full.count("sed \\\"s/")
        echo_write = len(re.findall(r'echo.*>(?!>)', full))
        tee_count = full.count(" tee ")

        # Check for actual patch content (did the sandbox get any file changes?)
        patch = data.get("metadata", {}).get("patch", "")
        has_patch = bool(patch and patch.strip())

        marker = "PASS" if score_val == 1.0 else "FAIL"
        print(f"{marker} {sid}: tools={tool_counts} sed={sed_count} has_patch={has_patch}")
        if has_patch:
            # Show first few lines of the ground truth patch
            patch_lines = patch.strip().split('\n')[:3]
            print(f"  Ground truth patch: {patch_lines[0][:100]}")
