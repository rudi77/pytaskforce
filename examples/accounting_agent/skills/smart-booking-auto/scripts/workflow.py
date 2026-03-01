"""Smart Booking Auto - Resumable LangGraph Workflow.

This workflow processes invoices through a deterministic pipeline:
  extract → compliance → rules → confidence → book/escalate

Human-in-the-loop interrupts:
  - Compliance errors → ask supplier via Telegram for missing fields
  - Low confidence / no rules → ask accountant via CLI for booking decision

Requires: ``uv sync --extra workflow`` (installs langgraph)

Usage in SKILL.md frontmatter::

    script: scripts/workflow.py
    script_engine: langgraph
"""

from __future__ import annotations

from typing import Any, TypedDict

# LangGraph imports - requires ``uv sync --extra workflow``
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class BookingState(TypedDict, total=False):
    """Typed state flowing through the workflow graph."""

    file_path: str
    markdown_content: str
    invoice_data: dict[str, Any]
    compliance_result: dict[str, Any]
    rule_result: dict[str, Any]
    confidence_result: dict[str, Any]
    learned_rule: dict[str, Any]
    audit_entry: dict[str, Any]


# ---------------------------------------------------------------------------
# Tool access helper
# ---------------------------------------------------------------------------


def _get_tool_executor(config: dict[str, Any]) -> Any:
    """Extract the Taskforce tool executor from the LangGraph config.

    The LangGraphAdapter stores the executor on the graph object as
    ``_taskforce_tool_executor``. It is also passed in the configurable
    dict for convenience.

    Returns a callable ``(tool_name, params) -> result`` or a no-op fallback.
    """
    # Try configurable first (preferred injection path)
    configurable = config.get("configurable", {})
    executor = configurable.get("tool_executor")
    if executor is not None:
        return executor

    # Fallback: no-op that logs the gap
    def _noop(name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"success": False, "error": f"No tool executor for {name}"}

    return _noop


# ---------------------------------------------------------------------------
# Node functions
#
# Each node receives (state, config) from LangGraph.  The ``config``
# dict carries the Taskforce tool executor injected by the adapter.
# ---------------------------------------------------------------------------


def extract(state: BookingState, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract markdown from PDF and parse structured invoice data."""
    tools = _get_tool_executor(config or {})
    md = tools("docling_extract", {"file_path": state["file_path"]})
    invoice = tools(
        "invoice_extract",
        {"markdown_content": md, "expected_currency": "EUR"},
    )
    return {"markdown_content": md, "invoice_data": invoice}


def check_compliance(state: BookingState, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check invoice compliance (§14 UStG).

    If critical errors are found, interrupts the workflow to ask the
    supplier (via Telegram) for missing mandatory fields. After resume,
    the supplier's response is merged into the invoice data.
    """
    tools = _get_tool_executor(config or {})
    result = tools("check_compliance", {"invoice_data": state["invoice_data"]})

    violations = result.get("violations", [])
    errors = [v for v in violations if v.get("severity") == "error"]

    if errors:
        field_list = "\n".join(
            f"- {e.get('field', '?')}: {e.get('description', '')} ({e.get('rule', '')})"
            for e in errors
        )
        answer = interrupt(
            {
                "question": (
                    "⚠️ Die Rechnung ist unvollständig.\n\n"
                    "Folgende Pflichtangaben nach §14 UStG fehlen:\n"
                    f"{field_list}\n\n"
                    "Bitte ergänzen Sie die fehlenden Angaben."
                ),
                "channel": "telegram",
            }
        )
        # Merge supplier's response into invoice data
        if isinstance(answer, dict):
            updated = {**state["invoice_data"], **answer}
        else:
            updated = {**state["invoice_data"], "supplier_response": str(answer)}
        return {"invoice_data": updated, "compliance_result": result}

    return {"compliance_result": result}


def apply_rules(state: BookingState, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply semantic rule engine for account assignment."""
    tools = _get_tool_executor(config or {})
    result = tools(
        "semantic_rule_engine",
        {"invoice_data": state["invoice_data"], "chart_of_accounts": "SKR03"},
    )
    return {"rule_result": result}


def evaluate_confidence(
    state: BookingState, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Evaluate booking confidence based on rule match quality."""
    tools = _get_tool_executor(config or {})
    rule_result = state.get("rule_result", {})
    rule_matches = rule_result.get("rule_matches", [])
    booking_proposals = rule_result.get("booking_proposals", [])
    result = tools(
        "confidence_evaluator",
        {
            "invoice_data": state["invoice_data"],
            "rule_match": rule_matches[0] if rule_matches else {},
            "booking_proposal": booking_proposals[0] if booking_proposals else {},
        },
    )
    return {"confidence_result": result}


def hitl_review(state: BookingState, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Human-in-the-loop review by the accountant.

    Interrupts the workflow to ask the accountant (via CLI / current session)
    for their booking decision.
    """
    tools = _get_tool_executor(config or {})
    rule_result = state.get("rule_result", {})
    booking_proposals = rule_result.get("booking_proposals", [])

    proposal_text = ""
    if booking_proposals:
        bp = booking_proposals[0]
        proposal_text = (
            f"\nBuchungsvorschlag: Konto {bp.get('debit_account', '?')} "
            f"an {bp.get('credit_account', '?')}, "
            f"Betrag: {bp.get('amount', '?')} EUR"
        )

    decision = interrupt(
        {
            "question": (
                "Buchungsvorschlag prüfen:\n"
                f"Lieferant: {state.get('invoice_data', {}).get('vendor_name', '?')}\n"
                f"Betrag: {state.get('invoice_data', {}).get('gross_amount', '?')} EUR"
                f"{proposal_text}\n\n"
                "Bitte bestätigen, korrigieren oder ablehnen."
            ),
            # channel=None → ask current session user (accountant in CLI)
        }
    )
    tools("hitl_review", {"action": "process", "user_decision": str(decision)})
    return {"hitl_decision": str(decision)}


def auto_book(state: BookingState, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Automatically book the invoice and learn the rule."""
    tools = _get_tool_executor(config or {})
    rule_result = state.get("rule_result", {})
    confidence_result = state.get("confidence_result", {})
    booking_proposals = rule_result.get("booking_proposals", [])

    # Learn rule for future auto-booking
    learned = tools(
        "rule_learning",
        {
            "action": "create_from_booking",
            "invoice_data": state["invoice_data"],
            "booking_proposal": booking_proposals[0] if booking_proposals else {},
            "confidence": confidence_result.get("overall_confidence", 0),
        },
    )

    # Audit log
    audit = tools(
        "audit_log",
        {
            "action": "booking_created",
            "invoice_data": state["invoice_data"],
            "booking_proposal": booking_proposals[0] if booking_proposals else {},
            "confidence": confidence_result.get("overall_confidence", 0),
            "auto_booked": True,
        },
    )

    return {"learned_rule": learned, "audit_entry": audit}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_rules(state: BookingState) -> str:
    """Route based on whether rules were found."""
    rule_result = state.get("rule_result", {})
    if rule_result.get("rules_applied", 0) == 0:
        return "hitl_review"
    return "evaluate_confidence"


def route_after_confidence(state: BookingState) -> str:
    """Route based on confidence evaluation result."""
    confidence_result = state.get("confidence_result", {})
    recommendation = confidence_result.get("recommendation", "hitl_review")
    if recommendation == "auto_book":
        return "auto_book"
    return "hitl_review"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def create_workflow() -> Any:
    """Create the smart booking workflow graph.

    This is the entrypoint called by Taskforce's WorkflowOrchestrator.

    Returns:
        Compiled LangGraph StateGraph.
    """
    graph = StateGraph(BookingState)

    graph.add_node("extract", extract)
    graph.add_node("check_compliance", check_compliance)
    graph.add_node("apply_rules", apply_rules)
    graph.add_node("evaluate_confidence", evaluate_confidence)
    graph.add_node("hitl_review", hitl_review)
    graph.add_node("auto_book", auto_book)

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "check_compliance")
    graph.add_edge("check_compliance", "apply_rules")
    graph.add_conditional_edges("apply_rules", route_after_rules)
    graph.add_conditional_edges("evaluate_confidence", route_after_confidence)
    graph.add_edge("hitl_review", END)
    graph.add_edge("auto_book", END)

    return graph.compile()
