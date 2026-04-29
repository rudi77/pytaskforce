"""
Analytics API Routes
====================

Token-usage and cost aggregations served from the persistent
``TokenLedger`` (SQLite). Powers the management-UI dashboard and
monitoring page.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from taskforce.api.schemas.analytics_schemas import (
    AgentUsageEntry,
    ConversationUsageCall,
    ConversationUsageResponse,
    CostSummaryResponse,
    ModelUsageEntry,
    TokenUsageBucket,
    TokenUsageResponse,
)
from taskforce.application.token_ledger import get_token_ledger

router = APIRouter()


@router.get(
    "/analytics/token-usage",
    response_model=TokenUsageResponse,
    summary="Aggregated token usage over time",
)
def token_usage(
    granularity: str = Query("day", pattern="^(day|hour|minute)$"),
    from_iso: str | None = Query(None, alias="from"),
    to_iso: str | None = Query(None, alias="to"),
    agent: str | None = None,
) -> TokenUsageResponse:
    ledger = get_token_ledger()
    buckets = ledger.aggregate_by_period(
        granularity=granularity,
        from_iso=from_iso,
        to_iso=to_iso,
        agent_id=agent,
    )
    return TokenUsageResponse(
        granularity=granularity,
        pricing_as_of=ledger.pricing.as_of,
        buckets=[
            TokenUsageBucket(
                bucket=b.bucket,
                prompt_tokens=b.prompt_tokens,
                completion_tokens=b.completion_tokens,
                total_tokens=b.total_tokens,
                cost_usd=b.cost_usd,
                call_count=b.call_count,
            )
            for b in buckets
        ],
    )


@router.get(
    "/analytics/cost-summary",
    response_model=CostSummaryResponse,
    summary="Today / week / month cost roll-up",
)
def cost_summary() -> CostSummaryResponse:
    ledger = get_token_ledger()
    summary = ledger.cost_summary()
    return CostSummaryResponse(
        today_usd=summary.today_usd,
        week_usd=summary.week_usd,
        month_usd=summary.month_usd,
        pricing_as_of=ledger.pricing.as_of,
        by_agent=[
            AgentUsageEntry(
                agent=a.agent,
                prompt_tokens=a.prompt_tokens,
                completion_tokens=a.completion_tokens,
                total_tokens=a.total_tokens,
                cost_usd=a.cost_usd,
            )
            for a in summary.by_agent
        ],
        by_model=[
            ModelUsageEntry(
                model=m.model,
                prompt_tokens=m.prompt_tokens,
                completion_tokens=m.completion_tokens,
                total_tokens=m.total_tokens,
                cost_usd=m.cost_usd,
            )
            for m in summary.by_model
        ],
    )


@router.get(
    "/analytics/conversations/{conversation_id}/usage",
    response_model=ConversationUsageResponse,
    summary="Per-conversation token usage breakdown",
)
def conversation_usage(conversation_id: str) -> ConversationUsageResponse:
    data = get_token_ledger().per_conversation(conversation_id)
    return ConversationUsageResponse(
        conversation_id=str(data["conversation_id"]),
        total_prompt=int(data["total_prompt"]),
        total_completion=int(data["total_completion"]),
        total_cost_usd=float(data["total_cost_usd"]),
        calls=[ConversationUsageCall(**call) for call in data["calls"]],
    )
