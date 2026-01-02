from enum import Enum
from typing import Any

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

def parse_task_status(value: Any) -> TaskStatus:
    text = str(value or "").strip().replace("-", "_").replace(" ", "_").upper()
    if not text:
        return TaskStatus.PENDING

    alias = {
        "OPEN": "PENDING",
        "TODO": "PENDING",
        "INPROGRESS": "IN_PROGRESS",
        "DONE": "COMPLETED",
        "COMPLETE": "COMPLETED",
        "FAIL": "FAILED",
    }
    normalized = alias.get(text, text)
    try:
        return TaskStatus[normalized]
    except KeyError:
        print(f"KeyError for {normalized}")
        return TaskStatus.PENDING

print(f"Parsing 'SKIPPED': {parse_task_status('SKIPPED')}")
print(f"Parsing 'Skipped': {parse_task_status('Skipped')}")
print(f"Parsing 'skipped': {parse_task_status('skipped')}")

