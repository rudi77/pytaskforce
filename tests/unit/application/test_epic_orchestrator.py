from taskforce.application.epic_orchestrator import EpicOrchestrator


def test_parse_tasks_from_json() -> None:
    orchestrator = EpicOrchestrator()
    output = (
        """
```json
[
  {
    "title": "Task A",
    "description": "Do A",
    "acceptance_criteria": ["done"]
  }
]
```
"""
    )
    tasks = orchestrator._parse_tasks(output, "planner")

    assert len(tasks) == 1
    assert tasks[0].title == "Task A"
    assert tasks[0].acceptance_criteria == ["done"]


def test_deduplicate_tasks() -> None:
    orchestrator = EpicOrchestrator()
    tasks = orchestrator._parse_tasks("- Task A\n- Task A", "planner")

    deduped = orchestrator._deduplicate_tasks(tasks)

    assert len(deduped) == 1


def test_parse_judge_decision() -> None:
    orchestrator = EpicOrchestrator()
    output = (
        "```json\n"
        "{ \"summary\": \"round ok\", \"continue\": true }\n"
        "```"
    )

    decision = orchestrator._parse_judge_decision(output)

    assert decision["summary"] == "round ok"
    assert decision["continue"] is True
