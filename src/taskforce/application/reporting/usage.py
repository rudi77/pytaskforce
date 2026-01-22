"""Usage tracking for enterprise billing and analytics.

This module provides usage tracking for tokens, API calls, and other
billable resources at the tenant and user level.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, date, timedelta
from enum import Enum
from collections import defaultdict
import uuid


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class UsageType(Enum):
    """Types of usage that can be tracked."""

    INPUT_TOKENS = "input_tokens"
    OUTPUT_TOKENS = "output_tokens"
    TOTAL_TOKENS = "total_tokens"
    API_CALLS = "api_calls"
    AGENT_EXECUTIONS = "agent_executions"
    TOOL_EXECUTIONS = "tool_executions"
    RAG_QUERIES = "rag_queries"
    STORAGE_BYTES = "storage_bytes"


@dataclass
class UsageRecord:
    """A single usage record for billing.

    Attributes:
        record_id: Unique identifier for this record
        tenant_id: Tenant ID
        user_id: Optional user ID
        usage_type: Type of usage
        quantity: Amount of usage
        model: Optional model name (for token usage)
        agent_id: Optional agent ID
        session_id: Optional session ID
        timestamp: When usage occurred
        metadata: Additional metadata
    """

    record_id: str
    tenant_id: str
    user_id: Optional[str]
    usage_type: UsageType
    quantity: int
    model: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "usage_type": self.usage_type.value,
            "quantity": self.quantity,
            "model": self.model,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageRecord":
        """Create from dictionary."""
        return cls(
            record_id=data["record_id"],
            tenant_id=data["tenant_id"],
            user_id=data.get("user_id"),
            usage_type=UsageType(data["usage_type"]),
            quantity=data["quantity"],
            model=data.get("model"),
            agent_id=data.get("agent_id"),
            session_id=data.get("session_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class UsageAggregation:
    """Aggregated usage statistics.

    Attributes:
        tenant_id: Tenant ID
        user_id: Optional user ID
        period_start: Start of aggregation period
        period_end: End of aggregation period
        totals: Dictionary of usage type to total quantity
        by_model: Token usage broken down by model
        by_agent: Usage broken down by agent
        record_count: Number of records aggregated
    """

    tenant_id: str
    user_id: Optional[str]
    period_start: datetime
    period_end: datetime
    totals: Dict[UsageType, int] = field(default_factory=dict)
    by_model: Dict[str, Dict[UsageType, int]] = field(default_factory=dict)
    by_agent: Dict[str, Dict[UsageType, int]] = field(default_factory=dict)
    record_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "totals": {k.value: v for k, v in self.totals.items()},
            "by_model": {
                model: {k.value: v for k, v in usage.items()}
                for model, usage in self.by_model.items()
            },
            "by_agent": {
                agent: {k.value: v for k, v in usage.items()}
                for agent, usage in self.by_agent.items()
            },
            "record_count": self.record_count,
        }


class UsageTracker:
    """Tracks and aggregates usage for billing.

    This class provides methods for recording individual usage events
    and aggregating them for reporting and billing purposes.
    """

    def __init__(self, max_records_in_memory: int = 100000):
        """Initialize the usage tracker.

        Args:
            max_records_in_memory: Maximum records to keep in memory
        """
        self._records: List[UsageRecord] = []
        self._max_records = max_records_in_memory

        # Quick lookup indexes
        self._by_tenant: Dict[str, List[UsageRecord]] = defaultdict(list)
        self._by_user: Dict[str, List[UsageRecord]] = defaultdict(list)

    def record_usage(
        self,
        tenant_id: str,
        usage_type: UsageType,
        quantity: int,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """Record a usage event.

        Args:
            tenant_id: Tenant ID
            usage_type: Type of usage
            quantity: Amount of usage
            user_id: Optional user ID
            model: Optional model name
            agent_id: Optional agent ID
            session_id: Optional session ID
            metadata: Additional metadata

        Returns:
            The created usage record
        """
        record = UsageRecord(
            record_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            usage_type=usage_type,
            quantity=quantity,
            model=model,
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata or {},
        )

        self._records.append(record)
        self._by_tenant[tenant_id].append(record)
        if user_id:
            self._by_user[user_id].append(record)

        # Prune if needed
        if len(self._records) > self._max_records:
            self._prune_old_records()

        return record

    def record_tokens(
        self,
        tenant_id: str,
        input_tokens: int,
        output_tokens: int,
        model: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[UsageRecord]:
        """Record token usage (convenience method).

        Args:
            tenant_id: Tenant ID
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name
            user_id: Optional user ID
            agent_id: Optional agent ID
            session_id: Optional session ID

        Returns:
            List of created usage records
        """
        records = []

        if input_tokens > 0:
            records.append(
                self.record_usage(
                    tenant_id=tenant_id,
                    usage_type=UsageType.INPUT_TOKENS,
                    quantity=input_tokens,
                    user_id=user_id,
                    model=model,
                    agent_id=agent_id,
                    session_id=session_id,
                )
            )

        if output_tokens > 0:
            records.append(
                self.record_usage(
                    tenant_id=tenant_id,
                    usage_type=UsageType.OUTPUT_TOKENS,
                    quantity=output_tokens,
                    user_id=user_id,
                    model=model,
                    agent_id=agent_id,
                    session_id=session_id,
                )
            )

        # Also record total
        total = input_tokens + output_tokens
        if total > 0:
            records.append(
                self.record_usage(
                    tenant_id=tenant_id,
                    usage_type=UsageType.TOTAL_TOKENS,
                    quantity=total,
                    user_id=user_id,
                    model=model,
                    agent_id=agent_id,
                    session_id=session_id,
                )
            )

        return records

    def record_agent_execution(
        self,
        tenant_id: str,
        agent_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageRecord:
        """Record an agent execution.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            user_id: Optional user ID
            session_id: Optional session ID
            metadata: Additional metadata

        Returns:
            The created usage record
        """
        return self.record_usage(
            tenant_id=tenant_id,
            usage_type=UsageType.AGENT_EXECUTIONS,
            quantity=1,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata,
        )

    def record_tool_execution(
        self,
        tenant_id: str,
        tool_name: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> UsageRecord:
        """Record a tool execution.

        Args:
            tenant_id: Tenant ID
            tool_name: Name of tool executed
            user_id: Optional user ID
            agent_id: Optional agent ID
            session_id: Optional session ID

        Returns:
            The created usage record
        """
        return self.record_usage(
            tenant_id=tenant_id,
            usage_type=UsageType.TOOL_EXECUTIONS,
            quantity=1,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            metadata={"tool_name": tool_name},
        )

    def get_aggregation(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
    ) -> UsageAggregation:
        """Get aggregated usage for a period.

        Args:
            tenant_id: Tenant ID
            start_date: Start of period
            end_date: End of period
            user_id: Optional user ID to filter by

        Returns:
            UsageAggregation with totals and breakdowns
        """
        # Filter records
        if user_id:
            records = self._by_user.get(user_id, [])
            records = [r for r in records if r.tenant_id == tenant_id]
        else:
            records = self._by_tenant.get(tenant_id, [])

        records = [
            r for r in records
            if start_date <= r.timestamp <= end_date
        ]

        # Aggregate
        agg = UsageAggregation(
            tenant_id=tenant_id,
            user_id=user_id,
            period_start=start_date,
            period_end=end_date,
            record_count=len(records),
        )

        for record in records:
            # Total
            if record.usage_type not in agg.totals:
                agg.totals[record.usage_type] = 0
            agg.totals[record.usage_type] += record.quantity

            # By model
            if record.model:
                if record.model not in agg.by_model:
                    agg.by_model[record.model] = {}
                if record.usage_type not in agg.by_model[record.model]:
                    agg.by_model[record.model][record.usage_type] = 0
                agg.by_model[record.model][record.usage_type] += record.quantity

            # By agent
            if record.agent_id:
                if record.agent_id not in agg.by_agent:
                    agg.by_agent[record.agent_id] = {}
                if record.usage_type not in agg.by_agent[record.agent_id]:
                    agg.by_agent[record.agent_id][record.usage_type] = 0
                agg.by_agent[record.agent_id][record.usage_type] += record.quantity

        return agg

    def get_daily_totals(
        self,
        tenant_id: str,
        start_date: date,
        end_date: date,
        user_id: Optional[str] = None,
    ) -> Dict[date, Dict[UsageType, int]]:
        """Get daily usage totals.

        Args:
            tenant_id: Tenant ID
            start_date: Start date
            end_date: End date
            user_id: Optional user ID filter

        Returns:
            Dictionary of date to usage totals
        """
        daily: Dict[date, Dict[UsageType, int]] = {}

        # Initialize all dates
        current = start_date
        while current <= end_date:
            daily[current] = {}
            current += timedelta(days=1)

        # Get records
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(
            tzinfo=timezone.utc
        )

        if user_id:
            records = self._by_user.get(user_id, [])
            records = [r for r in records if r.tenant_id == tenant_id]
        else:
            records = self._by_tenant.get(tenant_id, [])

        records = [
            r for r in records
            if start_dt <= r.timestamp <= end_dt
        ]

        # Aggregate by day
        for record in records:
            day = record.timestamp.date()
            if day not in daily:
                daily[day] = {}
            if record.usage_type not in daily[day]:
                daily[day][record.usage_type] = 0
            daily[day][record.usage_type] += record.quantity

        return daily

    def get_records(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        usage_type: Optional[UsageType] = None,
        limit: int = 1000,
    ) -> List[UsageRecord]:
        """Get raw usage records.

        Args:
            tenant_id: Tenant ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            user_id: Optional user ID filter
            usage_type: Optional usage type filter
            limit: Maximum records to return

        Returns:
            List of matching usage records
        """
        if user_id:
            records = self._by_user.get(user_id, [])
            records = [r for r in records if r.tenant_id == tenant_id]
        else:
            records = self._by_tenant.get(tenant_id, [])

        # Apply filters
        if start_date:
            records = [r for r in records if r.timestamp >= start_date]
        if end_date:
            records = [r for r in records if r.timestamp <= end_date]
        if usage_type:
            records = [r for r in records if r.usage_type == usage_type]

        # Sort by timestamp descending and limit
        records = sorted(records, key=lambda r: r.timestamp, reverse=True)
        return records[:limit]

    def _prune_old_records(self) -> None:
        """Remove oldest records to stay within memory limit."""
        # Keep most recent records
        excess = len(self._records) - self._max_records
        if excess <= 0:
            return

        # Sort by timestamp and remove oldest
        self._records.sort(key=lambda r: r.timestamp)
        to_remove = self._records[:excess]
        self._records = self._records[excess:]

        # Update indexes
        for record in to_remove:
            if record in self._by_tenant[record.tenant_id]:
                self._by_tenant[record.tenant_id].remove(record)
            if record.user_id and record in self._by_user[record.user_id]:
                self._by_user[record.user_id].remove(record)

    def clear(self, tenant_id: Optional[str] = None) -> int:
        """Clear usage records.

        Args:
            tenant_id: Optional tenant to clear (all if None)

        Returns:
            Number of records cleared
        """
        if tenant_id:
            count = len(self._by_tenant.get(tenant_id, []))
            if tenant_id in self._by_tenant:
                for record in self._by_tenant[tenant_id]:
                    self._records.remove(record)
                    if record.user_id and record in self._by_user[record.user_id]:
                        self._by_user[record.user_id].remove(record)
                del self._by_tenant[tenant_id]
            return count
        else:
            count = len(self._records)
            self._records = []
            self._by_tenant = defaultdict(list)
            self._by_user = defaultdict(list)
            return count
