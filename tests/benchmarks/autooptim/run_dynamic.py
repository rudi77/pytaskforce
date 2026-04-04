"""Helper to run a dynamic mission from a file, avoiding shell quoting issues."""
import sys
import os

if __name__ == "__main__":
    mission_file = sys.argv[1] if len(sys.argv) > 1 else None
    name = sys.argv[2] if len(sys.argv) > 2 else "dynamic"

    if not mission_file or not os.path.exists(mission_file):
        print(f"Usage: python run_dynamic.py <mission_file> [name]", file=sys.stderr)
        sys.exit(1)

    with open(mission_file, encoding="utf-8") as f:
        mission = f.read().strip()

    os.environ["EVAL_MISSION"] = mission
    sys.argv = ["eval_butler.py", "dynamic", "--name", name]

    # Import and run
    from tests.benchmarks.autooptim.eval_butler import _parse_args, main_dynamic
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main_dynamic(mission, name))
    finally:
        try:
            loop.close()
        except Exception:
            pass
        os._exit(0)
