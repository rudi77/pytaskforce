"""Pydantic schemas for the analytics + active-runs endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenUsageBucket(BaseModel):
    bucket: str = Field(..., description="ISO timestamp prefix (day/hour/minute)")
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    call_count: int


class TokenUsageResponse(BaseModel):
    granularity: str
    pricing_as_of: str | None = None
    buckets: list[TokenUsageBucket]


class AgentUsageEntry(BaseModel):
    agent: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class ModelUsageEntry(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class CostSummaryResponse(BaseModel):
    today_usd: float
    week_usd: float
    month_usd: float
    pricing_as_of: str | None = None
    by_agent: list[AgentUsageEntry]
    by_model: list[ModelUsageEntry]


class ConversationUsageCall(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    ts: str


class ConversationUsageResponse(BaseModel):
    conversation_id: str
    total_prompt: int
    total_completion: int
    total_cost_usd: float
    calls: list[ConversationUsageCall]


class ActiveRunResponse(BaseModel):
    session_id: str
    started_at: str
    profile: str | None = None
    agent_id: str | None = None
    conversation_id: str | None = None
    mission_preview: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    last_event: str = ""
    last_event_at: str


class ActiveRunsResponse(BaseModel):
    runs: list[ActiveRunResponse]
