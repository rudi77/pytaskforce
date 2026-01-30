# ADR 005: Epic Orchestration Pipeline

## Status
Accepted

## Context
Teams need to execute large epics by decomposing work into parallel tasks, running
workers independently, and consolidating changes through a judge step. The
system should align with a planner/worker/judge hierarchy and remain compatible
with Taskforce's clean architecture.

## Decision
We introduce an epic orchestration pipeline in the application layer:

- `EpicOrchestrator` coordinates planner, worker, and judge agents.
- Planner agents produce JSON task lists; optional sub-planners add scoped tasks.
- Tasks are dispatched via `MessageBusProtocol` (default: in-memory adapter).
- Worker agents execute tasks in isolated sessions.
- Judge agent reviews worker summaries and optionally commits changes.
- The judge can request another round; the orchestrator re-plans up to a max round limit.

Dedicated profiles (`planner`, `worker`, `judge`) are added for the pipeline.

## Consequences
- Epic workflows can run end-to-end using existing agent infrastructure.
- The pipeline is extensible (swap message bus adapters, adjust profiles).
- Judge commits are explicit and controlled by CLI flags.
