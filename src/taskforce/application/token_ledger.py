"""
Token Ledger
============

Persistent per-LLM-call ledger backed by SQLite. Powers the analytics
endpoints (``/api/v1/analytics/*``) so the management UI can render
historical token-usage and cost charts.

Design choices:

* SQLite over a JSON file — gives us cheap GROUP BY / time-bucket
  queries for chart aggregation.
* ``record()`` is the only write API; called from the LiteLLM
  TokenAnalyticsCallback.
* ``aggregate_by_period`` and ``aggregate_by_agent`` are pure read paths
  used by the routes.
* The ledger never raises into the LLM call path — record swallows
  ``sqlite3.Error`` to keep the executor robust.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

import structlog

from taskforce.application.pricing import PricingTable, get_pricing_table

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class LedgerEntry:
    timestamp: datetime
    session_id: str
    conversation_id: str | None
    agent_id: str | None
    profile: str | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class UsageBucket:
    bucket: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    call_count: int


@dataclass(frozen=True)
class AgentUsage:
    agent: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class ModelUsage:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class CostSummary:
    today_usd: float
    week_usd: float
    month_usd: float
    by_agent: list[AgentUsage]
    by_model: list[ModelUsage]


# ContextVar so the executor can stamp records that fly through
# LiteLLM with run-level metadata even though the callback is global.
_run_context: ContextVar[dict[str, str | None]] = ContextVar(
    "_token_ledger_run_context",
    default={"session_id": None, "conversation_id": None, "agent_id": None, "profile": None},
)


class TokenLedger:
    """SQLite-backed ledger of per-call token usage and cost."""

    def __init__(
        self,
        db_path: Path | None = None,
        pricing: PricingTable | None = None,
    ) -> None:
        self._db_path = db_path or _default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._pricing = pricing or get_pricing_table()
        self._lock = threading.Lock()
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def pricing(self) -> PricingTable:
        return self._pricing

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            # WAL keeps reads (analytics aggregations) from blocking the
            # writer (LiteLLM callback on the LLM hot path) under load.
            # synchronous=NORMAL is safe with WAL and avoids fsync per commit.
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.DatabaseError:  # pragma: no cover — defensive
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT,
                    conversation_id TEXT,
                    agent_id TEXT,
                    profile TEXT,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS llm_calls_ts ON llm_calls(ts)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS llm_calls_conversation ON llm_calls(conversation_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS llm_calls_agent ON llm_calls(agent_id)"
            )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        timestamp: datetime,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: str | None = None,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        profile: str | None = None,
    ) -> LedgerEntry | None:
        ctx = _run_context.get() or {}
        session_id = session_id or ctx.get("session_id")
        conversation_id = conversation_id or ctx.get("conversation_id")
        agent_id = agent_id or ctx.get("agent_id")
        profile = profile or ctx.get("profile")
        cost = self._pricing.cost(model, prompt_tokens, completion_tokens).cost_usd
        entry = LedgerEntry(
            timestamp=timestamp,
            session_id=session_id or "",
            conversation_id=conversation_id,
            agent_id=agent_id,
            profile=profile,
            model=model,
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
            cost_usd=cost,
        )
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO llm_calls (ts, session_id, conversation_id, agent_id, "
                    "profile, model, prompt_tokens, completion_tokens, cost_usd) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry.timestamp.isoformat(),
                        entry.session_id,
                        entry.conversation_id,
                        entry.agent_id,
                        entry.profile,
                        entry.model,
                        entry.prompt_tokens,
                        entry.completion_tokens,
                        entry.cost_usd,
                    ),
                )
        except sqlite3.Error:
            logger.warning("token_ledger_write_failed", exc_info=True)
            return None
        return entry

    # ------------------------------------------------------------------
    # Reads / aggregations
    # ------------------------------------------------------------------

    def aggregate_by_period(
        self,
        *,
        granularity: str = "day",
        from_iso: str | None = None,
        to_iso: str | None = None,
        agent_id: str | None = None,
    ) -> list[UsageBucket]:
        bucket_expr = _bucket_expression(granularity)
        params: list[object] = []
        where: list[str] = []
        if from_iso:
            where.append("ts >= ?")
            params.append(from_iso)
        if to_iso:
            where.append("ts <= ?")
            params.append(to_iso)
        if agent_id:
            where.append("agent_id = ?")
            params.append(agent_id)
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""

        sql = (
            f"SELECT {bucket_expr} AS bucket, "
            "SUM(prompt_tokens) AS prompt, SUM(completion_tokens) AS completion, "
            "SUM(prompt_tokens + completion_tokens) AS total, SUM(cost_usd) AS cost, "
            "COUNT(*) AS calls "
            f"FROM llm_calls{where_sql} GROUP BY bucket ORDER BY bucket"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            UsageBucket(
                bucket=str(row["bucket"]),
                prompt_tokens=int(row["prompt"] or 0),
                completion_tokens=int(row["completion"] or 0),
                total_tokens=int(row["total"] or 0),
                cost_usd=float(row["cost"] or 0.0),
                call_count=int(row["calls"] or 0),
            )
            for row in rows
        ]

    def aggregate_by_agent(
        self,
        *,
        from_iso: str | None = None,
        to_iso: str | None = None,
    ) -> list[AgentUsage]:
        params: list[object] = []
        where: list[str] = []
        if from_iso:
            where.append("ts >= ?")
            params.append(from_iso)
        if to_iso:
            where.append("ts <= ?")
            params.append(to_iso)
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        sql = (
            "SELECT COALESCE(agent_id, profile, '(unknown)') AS agent, "
            "SUM(prompt_tokens) AS prompt, SUM(completion_tokens) AS completion, "
            "SUM(prompt_tokens + completion_tokens) AS total, SUM(cost_usd) AS cost "
            f"FROM llm_calls{where_sql} GROUP BY agent ORDER BY cost DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            AgentUsage(
                agent=row["agent"],
                prompt_tokens=int(row["prompt"] or 0),
                completion_tokens=int(row["completion"] or 0),
                total_tokens=int(row["total"] or 0),
                cost_usd=float(row["cost"] or 0.0),
            )
            for row in rows
        ]

    def aggregate_by_model(
        self,
        *,
        from_iso: str | None = None,
        to_iso: str | None = None,
    ) -> list[ModelUsage]:
        params: list[object] = []
        where: list[str] = []
        if from_iso:
            where.append("ts >= ?")
            params.append(from_iso)
        if to_iso:
            where.append("ts <= ?")
            params.append(to_iso)
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        sql = (
            "SELECT model, "
            "SUM(prompt_tokens) AS prompt, SUM(completion_tokens) AS completion, "
            "SUM(prompt_tokens + completion_tokens) AS total, SUM(cost_usd) AS cost "
            f"FROM llm_calls{where_sql} GROUP BY model ORDER BY cost DESC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            ModelUsage(
                model=row["model"] or "unknown",
                prompt_tokens=int(row["prompt"] or 0),
                completion_tokens=int(row["completion"] or 0),
                total_tokens=int(row["total"] or 0),
                cost_usd=float(row["cost"] or 0.0),
            )
            for row in rows
        ]

    def cost_summary(self) -> CostSummary:
        from datetime import timedelta, timezone

        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week = today - timedelta(days=7)
        month = today - timedelta(days=30)

        def _sum(since: datetime) -> float:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE ts >= ?",
                    (since.isoformat(),),
                ).fetchone()
            return float(row[0] or 0.0)

        return CostSummary(
            today_usd=_sum(today),
            week_usd=_sum(week),
            month_usd=_sum(month),
            by_agent=self.aggregate_by_agent(from_iso=month.isoformat()),
            by_model=self.aggregate_by_model(from_iso=month.isoformat()),
        )

    def per_session(self, session_id: str) -> dict[str, object]:
        """Aggregate token usage and cost for a single session id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(prompt_tokens), 0) AS p, "
                "COALESCE(SUM(completion_tokens), 0) AS c, "
                "COALESCE(SUM(cost_usd), 0.0) AS cost "
                "FROM llm_calls WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return {
            "session_id": session_id,
            "prompt_tokens": int(row["p"] or 0) if row else 0,
            "completion_tokens": int(row["c"] or 0) if row else 0,
            "cost_usd": float(row["cost"] or 0.0) if row else 0.0,
        }

    def per_conversation(self, conversation_id: str) -> dict[str, object]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT model, prompt_tokens, completion_tokens, cost_usd, ts "
                "FROM llm_calls WHERE conversation_id = ? ORDER BY ts",
                (conversation_id,),
            ).fetchall()
        if not rows:
            return {
                "conversation_id": conversation_id,
                "total_prompt": 0,
                "total_completion": 0,
                "total_cost_usd": 0.0,
                "calls": [],
            }
        total_prompt = sum(int(row["prompt_tokens"] or 0) for row in rows)
        total_completion = sum(int(row["completion_tokens"] or 0) for row in rows)
        total_cost = sum(float(row["cost_usd"] or 0.0) for row in rows)
        calls = [
            {
                "model": row["model"],
                "prompt_tokens": int(row["prompt_tokens"] or 0),
                "completion_tokens": int(row["completion_tokens"] or 0),
                "cost_usd": float(row["cost_usd"] or 0.0),
                "ts": row["ts"],
            }
            for row in rows
        ]
        return {
            "conversation_id": conversation_id,
            "total_prompt": total_prompt,
            "total_completion": total_completion,
            "total_cost_usd": total_cost,
            "calls": calls,
        }


def _bucket_expression(granularity: str) -> str:
    g = (granularity or "day").lower()
    if g == "hour":
        return "substr(ts, 1, 13)"
    if g == "minute":
        return "substr(ts, 1, 16)"
    return "substr(ts, 1, 10)"  # day


def _default_db_path() -> Path:
    override = os.environ.get("TASKFORCE_ANALYTICS_DB")
    if override:
        return Path(override).expanduser()
    return Path(".taskforce") / "analytics.db"


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_ledger: TokenLedger | None = None


def get_token_ledger() -> TokenLedger:
    global _ledger
    if _ledger is None:
        _ledger = TokenLedger()
    return _ledger


def reset_token_ledger() -> None:
    global _ledger
    _ledger = None


def reset_db_for_tests(path: Path) -> TokenLedger:
    global _ledger
    _ledger = TokenLedger(db_path=path)
    return _ledger


# ------------------------------------------------------------------
# Run context — used by the executor to attach session/conversation/agent
# metadata to records that flow through the LiteLLM callback.
# ------------------------------------------------------------------


@contextmanager
def run_context(
    *,
    session_id: str | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    profile: str | None = None,
) -> Iterator[None]:
    token = _run_context.set(
        {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "profile": profile,
        }
    )
    try:
        yield
    finally:
        _run_context.reset(token)


def get_run_context() -> dict[str, str | None]:
    return dict(_run_context.get() or {})


__all__ = [
    "AgentUsage",
    "CostSummary",
    "LedgerEntry",
    "ModelUsage",
    "TokenLedger",
    "UsageBucket",
    "get_run_context",
    "get_token_ledger",
    "reset_db_for_tests",
    "reset_token_ledger",
    "run_context",
]
