"""LangGraph workflow for smart-booking-auto skill.

This PoC executes the same core steps as the declarative workflow but with an
explicit graph so pauses/branches are represented as workflow state transitions.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[Any]]


class SmartBookingState(TypedDict, total=False):
    """Runtime state for smart booking auto workflow."""

    input: dict[str, Any]
    outputs: dict[str, Any]
    steps_executed: list[dict[str, Any]]
    aborted: bool
    error: str | None
    switch_to_skill: str | None
    waiting_for_input: dict[str, Any] | None
    resume_payload: dict[str, Any] | None


async def run_smart_booking_auto_workflow(
    *,
    tool_executor: ToolExecutor,
    input_vars: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    """Run smart-booking-auto as a LangGraph workflow."""
    del workflow
    graph = StateGraph(SmartBookingState)

    async def bootstrap(state: SmartBookingState) -> SmartBookingState:
        checkpoint_outputs = state["input"].get("checkpoint_outputs")
        resume_payload = state["input"].get("resume_payload")
        if isinstance(checkpoint_outputs, dict):
            state.setdefault("outputs", {}).update(checkpoint_outputs)
        if isinstance(resume_payload, dict):
            state["resume_payload"] = resume_payload
        return state

    def bootstrap_router(state: SmartBookingState) -> Literal["resume", "fresh"]:
        return "resume" if isinstance(state.get("resume_payload"), dict) else "fresh"

    async def run_docling(state: SmartBookingState) -> SmartBookingState:
        file_path = state["input"].get("file_path")
        if not file_path:
            return _abort(state, "Missing input.file_path")
        return await _run_step(
            state,
            tool_executor=tool_executor,
            tool_name="docling_extract",
            params={"file_path": file_path},
            output_key="markdown_content",
            abort_on_error=True,
        )

    async def run_invoice_extract(state: SmartBookingState) -> SmartBookingState:
        return await _run_step(
            state,
            tool_executor=tool_executor,
            tool_name="invoice_extract",
            params={
                "markdown_content": state["outputs"].get("markdown_content"),
                "expected_currency": "EUR",
            },
            output_key="invoice_data",
            abort_on_error=True,
        )

    async def run_compliance(state: SmartBookingState) -> SmartBookingState:
        return await _run_step(
            state,
            tool_executor=tool_executor,
            tool_name="check_compliance",
            params={"invoice_data": state["outputs"].get("invoice_data")},
            output_key="compliance_result",
            abort_on_error=True,
        )

    def compliance_router(state: SmartBookingState) -> Literal["missing_fields", "rules", "end"]:
        if state.get("aborted"):
            return "end"
        result = state["outputs"].get("compliance_result", {})
        issues = result.get("issues", []) if isinstance(result, dict) else []
        has_hard_error = any(
            isinstance(issue, dict) and issue.get("severity") == "error" for issue in issues
        )
        return "missing_fields" if has_hard_error else "rules"

    async def ask_missing_fields(state: SmartBookingState) -> SmartBookingState:
        invoice_data = state["outputs"].get("invoice_data", {})
        params: dict[str, Any] = {
            "question": (
                "⚠️ Rechnung "
                f"{invoice_data.get('invoice_number', 'unbekannt')} "
                f"von {invoice_data.get('vendor_name', 'unbekannt')} ist unvollständig. "
                "Bitte fehlende Pflichtangaben nach §14 UStG ergänzen."
            )
        }
        recipient_id = state["input"].get("recipient_id")
        if recipient_id:
            params["channel"] = "telegram"
            params["recipient_id"] = recipient_id

        ask_result = await _safe_execute(tool_executor, "ask_user", params)
        _append_step(state, "ask_user", ask_result)
        state["waiting_for_input"] = {
            "node_id": "missing_fields",
            "blocking_reason": "missing_supplier_data",
            "required_inputs": {"required": ["supplier_reply"]},
            "question": params["question"],
        }
        state["error"] = "Waiting for supplier clarification"
        return state

    async def apply_resume_payload(state: SmartBookingState) -> SmartBookingState:
        resume_payload = state.get("resume_payload", {})
        if not isinstance(resume_payload, dict):
            return _abort(state, "Missing resume payload")
        compliance = state.setdefault("outputs", {}).setdefault("compliance_result", {})
        if isinstance(compliance, dict):
            compliance["resume_payload"] = resume_payload
        invoice_data = state.setdefault("outputs", {}).setdefault("invoice_data", {})
        if isinstance(invoice_data, dict):
            invoice_data["supplier_reply"] = resume_payload.get("supplier_reply")
        state["waiting_for_input"] = None
        return state

    async def run_rules(state: SmartBookingState) -> SmartBookingState:
        return await _run_step(
            state,
            tool_executor=tool_executor,
            tool_name="semantic_rule_engine",
            params={
                "invoice_data": state["outputs"].get("invoice_data"),
                "chart_of_accounts": "SKR03",
            },
            output_key="rule_result",
        )

    def rules_router(state: SmartBookingState) -> Literal["hitl", "confidence", "end"]:
        if state.get("aborted"):
            return "end"
        if state["outputs"].get("rule_result", {}).get("rules_applied", 0) == 0:
            return "hitl"
        return "confidence"

    async def run_confidence(state: SmartBookingState) -> SmartBookingState:
        rule_result = state["outputs"].get("rule_result", {})
        matches = rule_result.get("rule_matches", [])
        proposals = rule_result.get("booking_proposals", [])
        if not matches or not proposals:
            return _abort(state, "Missing rule match or booking proposal for confidence evaluation")
        return await _run_step(
            state,
            tool_executor=tool_executor,
            tool_name="confidence_evaluator",
            params={
                "invoice_data": state["outputs"].get("invoice_data"),
                "rule_match": matches[0],
                "booking_proposal": proposals[0],
            },
            output_key="confidence_result",
            abort_on_error=True,
        )

    def confidence_router(state: SmartBookingState) -> Literal["hitl", "rule_learning", "end"]:
        if state.get("aborted"):
            return "end"
        rec = state["outputs"].get("confidence_result", {}).get("recommendation")
        return "hitl" if rec == "hitl_review" else "rule_learning"

    async def run_rule_learning(state: SmartBookingState) -> SmartBookingState:
        rule_result = state["outputs"].get("rule_result", {})
        proposals = rule_result.get("booking_proposals", [])
        if not proposals:
            return state
        confidence = state["outputs"].get("confidence_result", {})
        return await _run_step(
            state,
            tool_executor=tool_executor,
            tool_name="rule_learning",
            params={
                "action": "create_from_booking",
                "invoice_data": state["outputs"].get("invoice_data"),
                "booking_proposal": proposals[0],
                "confidence": confidence.get("overall_confidence"),
            },
            output_key="learned_rule",
            optional=True,
        )

    async def run_audit_log(state: SmartBookingState) -> SmartBookingState:
        rule_result = state["outputs"].get("rule_result", {})
        proposals = rule_result.get("booking_proposals", [])
        if not proposals:
            return _abort(state, "Missing booking proposal for audit logging")
        confidence = state["outputs"].get("confidence_result", {})
        return await _run_step(
            state,
            tool_executor=tool_executor,
            tool_name="audit_log",
            params={
                "operation": "booking_proposed",
                "details": {
                    "invoice_data": state["outputs"].get("invoice_data"),
                    "booking_proposal": proposals[0],
                    "confidence": confidence.get("overall_confidence"),
                    "auto_booked": True,
                },
            },
            output_key="audit_entry",
        )

    async def route_to_hitl(state: SmartBookingState) -> SmartBookingState:
        state["switch_to_skill"] = "smart-booking-hitl"
        return state

    graph.add_node("bootstrap", bootstrap)
    graph.add_node("resume_apply", apply_resume_payload)
    graph.add_node("docling", run_docling)
    graph.add_node("invoice_extract", run_invoice_extract)
    graph.add_node("compliance", run_compliance)
    graph.add_node("missing_fields", ask_missing_fields)
    graph.add_node("rules", run_rules)
    graph.add_node("confidence", run_confidence)
    graph.add_node("rule_learning", run_rule_learning)
    graph.add_node("audit_log", run_audit_log)
    graph.add_node("hitl", route_to_hitl)

    graph.set_entry_point("bootstrap")
    graph.add_conditional_edges(
        "bootstrap",
        bootstrap_router,
        {"resume": "resume_apply", "fresh": "docling"},
    )
    graph.add_edge("resume_apply", "rules")
    graph.add_edge("docling", "invoice_extract")
    graph.add_edge("invoice_extract", "compliance")
    graph.add_conditional_edges(
        "compliance",
        compliance_router,
        {"missing_fields": "missing_fields", "rules": "rules", "end": END},
    )
    graph.add_edge("missing_fields", END)
    graph.add_conditional_edges(
        "rules",
        rules_router,
        {"hitl": "hitl", "confidence": "confidence", "end": END},
    )
    graph.add_edge("hitl", END)
    graph.add_conditional_edges(
        "confidence",
        confidence_router,
        {"hitl": "hitl", "rule_learning": "rule_learning", "end": END},
    )
    graph.add_edge("rule_learning", "audit_log")
    graph.add_edge("audit_log", END)

    compiled = graph.compile()
    final_state = await compiled.ainvoke(
        {
            "input": input_vars,
            "outputs": {},
            "steps_executed": [],
            "aborted": False,
            "error": None,
            "switch_to_skill": None,
            "waiting_for_input": None,
            "resume_payload": None,
        }
    )

    return {
        "outputs": final_state.get("outputs", {}),
        "steps_executed": final_state.get("steps_executed", []),
        "aborted": final_state.get("aborted", False),
        "error": final_state.get("error"),
        "switch_to_skill": final_state.get("switch_to_skill"),
        "waiting_for_input": final_state.get("waiting_for_input"),
    }


async def _run_step(
    state: SmartBookingState,
    *,
    tool_executor: ToolExecutor,
    tool_name: str,
    params: dict[str, Any],
    output_key: str | None = None,
    abort_on_error: bool = False,
    optional: bool = False,
) -> SmartBookingState:
    result = await _safe_execute(tool_executor, tool_name, params)
    _append_step(state, tool_name, result)

    if _is_error_result(result):
        if optional:
            return state
        if abort_on_error:
            return _abort(state, f"{tool_name} failed: {result.get('error', 'unknown error')}")
        return state

    if output_key:
        state.setdefault("outputs", {})[output_key] = result
    return state


def _append_step(state: SmartBookingState, tool_name: str, result: Any) -> None:
    state.setdefault("steps_executed", []).append(
        {
            "tool": tool_name,
            "success": not _is_error_result(result),
            "result_summary": _summarize_result(result),
        }
    )


async def _safe_execute(tool_executor: ToolExecutor, tool_name: str, params: dict[str, Any]) -> Any:
    try:
        return await tool_executor(tool_name, params)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}


def _is_error_result(result: Any) -> bool:
    return isinstance(result, dict) and (result.get("success") is False or "error" in result)


def _abort(state: SmartBookingState, message: str) -> SmartBookingState:
    state["aborted"] = True
    state["error"] = message
    return state


def _summarize_result(result: Any) -> str:
    if isinstance(result, dict):
        if "error" in result:
            return f"Error: {result['error'][:100]}"
        if "success" in result:
            return "Success" if result["success"] else "Failed"
        return f"Keys: {', '.join(list(result.keys())[:5])}"
    return str(result)[:100]
