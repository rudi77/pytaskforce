"""Show the completion text and event types for one sample."""
import zipfile
import json

log = "logs/2026-03-10T14-58-53+00-00_swe-bench-verified-mini_B6X8HREAvz3cr2zRD6E59o.eval"

with zipfile.ZipFile(log) as z:
    # Pick a sample with many pytest mentions
    data = json.loads(z.read("samples/astropy__astropy-7336_epoch_1.json").decode())

    # Show output completion
    output = data.get("output", {})
    completion = output.get("completion", "")
    print("=== OUTPUT COMPLETION ===")
    print(completion[:2000])
    print()

    # Show event types
    events = data.get("events", [])
    print(f"=== EVENTS ({len(events)}) ===")
    for i, evt in enumerate(events[:15]):
        evt_type = evt.get("event", "?")
        evt_id = evt.get("type", "")
        name = evt.get("name", "")
        # Try to get content preview
        content = ""
        if "input" in evt:
            content = str(evt["input"])[:100]
        elif "content" in evt:
            content = str(evt["content"])[:100]
        elif "text" in evt:
            content = str(evt["text"])[:100]
        print(f"  [{i}] event={evt_type} type={evt_id} name={name} | {content}")

    # Search for shell commands containing pytest in the full text
    full = json.dumps(data)
    import re
    # Find shell tool calls with pytest
    patterns = [
        r'python -m pytest[^"]*',
        r'pytest [^"]*',
        r'"command":\s*"[^"]*pytest[^"]*"',
    ]
    print("\n=== PYTEST COMMAND MATCHES ===")
    for pat in patterns:
        matches = re.findall(pat, full)
        for m in matches[:5]:
            print(f"  {m[:150]}")
