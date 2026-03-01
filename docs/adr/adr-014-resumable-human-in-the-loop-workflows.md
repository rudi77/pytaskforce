# ADR 014: Resumable Human-in-the-Loop Workflow Checkpoints

- **Status:** Accepted
- **Date:** 2026-03-01
- **Owners:** Core Platform

## Context

Some automation scenarios (for example accounting auto-booking) cannot complete end-to-end without external clarification. Typical blockers include:

- Missing mandatory invoice fields that require supplier feedback.
- Ambiguous booking decisions that require a bookkeeper's approval.
- Compliance checks requiring explicit human sign-off.

A pure synchronous LLM loop wastes tokens while waiting and often re-computes context after each interaction. We need a generic mechanism that allows any workflow engine (LangGraph or equivalent) to pause, request input, and resume with minimal additional tokens.

## Decision

We standardize a **resumable checkpoint protocol** for long-running workflows.

### 1) Split execution into deterministic states

Each workflow step writes a typed `WorkflowState` snapshot (JSON serializable) containing:

- `run_id`
- `node_id`
- `status` (`running`, `waiting_external`, `completed`, `failed`)
- `blocking_reason` (`missing_supplier_data`, `needs_bookkeeper_decision`, ...)
- `required_inputs` (structured schema for what is needed)
- `next_deadline` (optional SLA for escalation)

### 2) Introduce a generic Wait Gate node

Workflows use a dedicated `wait_for_input` node that:

- Persists checkpoint + outstanding question.
- Emits an outbound message via `CommunicationService`.
- Returns control immediately instead of keeping an LLM loop alive.

### 3) Resume through event ingestion

Inbound replies (bookkeeper or supplier) are mapped to a `ResumeEvent`:

- `run_id`
- `input_type`
- `payload`
- `sender_metadata`

A `WorkflowResumer` loads the latest checkpoint, validates `payload` against `required_inputs`, injects data into `WorkflowState`, and continues from `node_id`.

### 4) Keep prompts minimal and local

Only nodes that require reasoning call the LLM. Validation, enrichment, routing, and persistence remain deterministic Python code. Human responses are normalized to compact typed payloads to avoid replaying long chat transcripts.

## Why this is generic (not accounting-specific)

The mechanism is intentionally domain-agnostic:

- **Engine-agnostic runtime**: the contract only needs `checkpoint(state)` and `resume(run_id, input)` semantics, so it maps to LangGraph, Temporal, Prefect, Celery chains, or a custom state machine.
- **Domain-neutral state schema**: fields like `blocking_reason`, `required_inputs`, and `node_id` are generic and can model approvals, missing documents, compliance checks, KYC exceptions, support escalations, or onboarding tasks.
- **Channel-neutral communication**: the outbound request can be sent via email, Teams, Slack, API callback, or ticket system, as long as replies can be normalized into `ResumeEvent`.
- **Policy plug-ins**: deadline/escalation/idempotency policies are configured, not hardcoded for accounting.

This keeps one reusable mechanism for many business processes.

## How it works (step-by-step)

1. A workflow executes deterministic nodes (`extract`, `validate`, `enrich`, `decide`, ...).
2. If all required data is available, it continues normally.
3. If data/decision is missing, the workflow enters `wait_for_input`.
4. `wait_for_input` persists a checkpoint with:
   - current `node_id`
   - normalized `blocking_reason`
   - machine-readable `required_inputs` schema
5. The system sends a structured question to the right actor (human/system).
6. Execution stops immediately (no active LLM loop, no token burn while waiting).
7. When a reply arrives, integration code converts it into a typed `ResumeEvent`.
8. `WorkflowResumer` validates payload against `required_inputs`.
9. On success, state is merged and execution resumes from the saved `node_id` (not from scratch).
10. On invalid/missing input, workflow stays in waiting state and emits a refined follow-up question.

### Minimal protocol contract

To reuse this pattern in any use case, keep only these primitives:

- `create_checkpoint(run_id, node_id, state, required_inputs, blocking_reason)`
- `send_request(run_id, recipient, question, required_inputs)`
- `ingest_resume_event(run_id, payload, sender_metadata)`
- `validate_resume_payload(required_inputs, payload)`
- `resume_from_checkpoint(run_id)`

Everything else (workflow engine, UI, channels, storage) remains replaceable.

## Consequences

### Positive

- Lower token usage and latency for interrupted workflows.
- Better reliability for long-running, asynchronous business processes.
- Reusable pattern across accounting, procurement, onboarding, and support.

### Trade-offs

- Requires durable checkpoint storage and schema versioning.
- Adds lifecycle states to monitor (`waiting_external`, `resumed`, `expired`).
- Needs idempotency safeguards for duplicate inbound events.

## Minimal Implementation Sketch

1. Add `WorkflowCheckpointStore` interface + file/db adapter.
2. Add `WaitGate` utility callable from any workflow node.
3. Add `POST /api/v1/workflows/{run_id}/resume` endpoint for inbound events.
4. Add timeout policy (`next_deadline`) with escalation handler.
5. Add one shared validator for `required_inputs` schema.

## Example mapping: Accounting Smart Booking

For smart booking auto mode:

- If confidence >= threshold and all mandatory fields exist: auto-post.
- Else enter `waiting_external` with one of:
  - `needs_bookkeeper_decision` (send booking proposals + options)
  - `missing_supplier_data` (send supplier clarification request template)
- Resume run when response is received; continue from classification/decision node without rerunning extraction.

This keeps the workflow fast and cheap while preserving controlled human intervention.


## Implementation Status

Implemented in Taskforce:

- File-backed `WorkflowCheckpointStore` for resumable workflow state.
- `WorkflowRuntimeService` for creating wait checkpoints and applying resume events.
- API routes: `POST /api/v1/workflows/wait`, `GET /api/v1/workflows/{run_id}`, `POST /api/v1/workflows/{run_id}/resume`, and `POST /api/v1/workflows/{run_id}/resume-and-continue`.
- Engine-backed skills (e.g. LangGraph PoC) can emit `waiting_for_input`; `activate_skill` persists checkpoints and returns `run_id` for later resume.
