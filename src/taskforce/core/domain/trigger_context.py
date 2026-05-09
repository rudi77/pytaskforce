"""ContextVar carrying the trigger origin of the active agent execution.

The approval gate (``LeanAgent._maybe_request_approval``) consults
this ContextVar to tell two situations apart that look identical at
the tool layer:

* **Interactive chat / API call.** A human just asked for this; the
  approval queue is the right gate — wait for an admin decision.
* **Scheduler-fired workflow run.** Nobody is at the keyboard at the
  moment of the call; the operator already vetted the workflow at
  design time. Asking for an interactive approval here just makes the
  call time out and the workflow silently fail.

The scheduler dispatcher (``application/scheduler_dispatcher.py``)
wraps each ``EXECUTE_WORKFLOW`` run with
``trigger_origin("scheduled_workflow")``. Tools that opt in via
``BaseTool.tool_auto_approve_for_origins`` are auto-approved when the
active origin matches one of their declared origins. Everything else
keeps falling through to the interactive approval queue.

The ContextVar pattern (rather than a kwarg threaded through
``execute_mission`` → ``execute_stream`` → ``_execute_tool``) keeps
existing call sites unchanged: a value set in the dispatcher's task
propagates automatically through every ``await``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


# Well-known origins. These are values, not an Enum, so plugins can
# coin their own (e.g. ``"webhook"``, ``"butler_rule"``) without
# importing from this module.
SCHEDULED_WORKFLOW_ORIGIN = "scheduled_workflow"


_CURRENT_TRIGGER_ORIGIN: ContextVar[str | None] = ContextVar(
    "taskforce.trigger_origin", default=None
)


def get_trigger_origin() -> str | None:
    """Return the active trigger origin or ``None`` for interactive flows."""
    return _CURRENT_TRIGGER_ORIGIN.get()


@contextmanager
def trigger_origin(origin: str) -> Iterator[None]:
    """Bind ``origin`` for the duration of the ``with`` block.

    Restores the previous value (typically ``None``) on exit, so a
    scheduler-triggered run leaves no residue for the next thing the
    event loop schedules.
    """
    token = _CURRENT_TRIGGER_ORIGIN.set(origin)
    try:
        yield
    finally:
        _CURRENT_TRIGGER_ORIGIN.reset(token)


__all__ = [
    "SCHEDULED_WORKFLOW_ORIGIN",
    "get_trigger_origin",
    "trigger_origin",
]
