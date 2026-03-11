"""Inspect the structure of a single sample to understand message format."""
import zipfile
import json

log = "logs/2026-03-10T14-58-53+00-00_swe-bench-verified-mini_B6X8HREAvz3cr2zRD6E59o.eval"

with zipfile.ZipFile(log) as z:
    data = json.loads(z.read("samples/astropy__astropy-12907_epoch_1.json").decode())

    # Print top-level keys
    print("Top-level keys:", list(data.keys()))
    print()

    messages = data.get("messages", [])
    print(f"Messages count: {len(messages)}")
    if messages:
        print(f"First message keys: {list(messages[0].keys()) if isinstance(messages[0], dict) else type(messages[0])}")
        # Show first few messages structure
        for i, msg in enumerate(messages[:5]):
            if isinstance(msg, dict):
                role = msg.get("role", "?")
                content_preview = str(msg.get("content", ""))[:100]
                has_tool_calls = "tool_calls" in msg
                print(f"  msg[{i}]: role={role} has_tool_calls={has_tool_calls} content={content_preview}")
            else:
                print(f"  msg[{i}]: {type(msg)}")

    # Check if there's an 'events' or 'transcript' key
    for key in ["events", "transcript", "steps", "output", "metadata"]:
        val = data.get(key)
        if val:
            if isinstance(val, list):
                print(f"\n{key}: list of {len(val)} items")
                if val:
                    print(f"  first item type: {type(val[0])}")
                    if isinstance(val[0], dict):
                        print(f"  first item keys: {list(val[0].keys())}")
            elif isinstance(val, dict):
                print(f"\n{key}: dict with keys {list(val.keys())[:10]}")
            else:
                print(f"\n{key}: {type(val)} = {str(val)[:200]}")
