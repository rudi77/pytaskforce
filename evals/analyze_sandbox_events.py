"""Analyze sandbox events to find actual file modifications."""
import zipfile
import json
import re

log = "logs/2026-03-10T17-07-21+00-00_swe-bench-verified-mini_TSHfzaL5ULRtFxjbwPEjKr.eval"

with zipfile.ZipFile(log) as z:
    # Look at one passing and one failing sample in detail
    for sample_name in [
        "samples/astropy__astropy-12907_epoch_1.json",  # PASS
        "samples/astropy__astropy-13033_epoch_1.json",  # FAIL (tested but 0 edits)
        "samples/astropy__astropy-13236_epoch_1.json",  # FAIL (no tests, admits not done)
        "samples/astropy__astropy-13579_epoch_1.json",  # FAIL (tested 3x, claims resolved)
    ]:
        data = json.loads(z.read(sample_name).decode())
        sid = data.get("id", "?")
        scores = data.get("scores", {})
        score_val = 0
        if isinstance(scores, dict):
            sv = scores.get("swe_bench_scorer", {})
            score_val = sv.get("value", 0) if isinstance(sv, dict) else sv

        events = data.get("events", [])
        print(f"{'='*70}")
        print(f"{'PASS' if score_val else 'FAIL'}: {sid} ({len(events)} events)")

        # Categorize sandbox events
        sandbox_events = [e for e in events if e.get("event") == "sandbox"]
        print(f"  Sandbox events: {len(sandbox_events)}")

        for i, evt in enumerate(sandbox_events[:30]):
            # Try to get the content/input of each sandbox event
            content = evt.get("content", "")
            input_data = evt.get("input", "")
            output_data = evt.get("output", "")

            # Combine all text content for inspection
            all_text = json.dumps(evt)

            # Classify what the sandbox event does
            if "edit" in all_text.lower() and ("old_string" in all_text or "new_string" in all_text):
                print(f"  [{i}] EDIT: {all_text[:200]}")
            elif "write_file" in all_text or "file_write" in all_text:
                print(f"  [{i}] WRITE: {all_text[:200]}")
            elif "pytest" in all_text:
                print(f"  [{i}] TEST: {all_text[:150]}")
            elif "git diff" in all_text:
                print(f"  [{i}] GIT_DIFF: {all_text[:150]}")
            elif "git checkout" in all_text:
                print(f"  [{i}] REVERT: {all_text[:150]}")
            elif "grep" in all_text and len(all_text) < 500:
                print(f"  [{i}] GREP: {all_text[:150]}")

        # Show all sandbox event keys for first event
        if sandbox_events:
            print(f"  First sandbox event keys: {list(sandbox_events[0].keys())}")
            print(f"  First sandbox event preview: {json.dumps(sandbox_events[0])[:300]}")
        print()
