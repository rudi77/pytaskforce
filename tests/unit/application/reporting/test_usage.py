"""Tests for usage tracking."""

import pytest
from datetime import datetime, timezone, timedelta
from taskforce.application.reporting.usage import (
    UsageType,
    UsageRecord,
    UsageAggregation,
    UsageTracker,
)


class TestUsageType:
    """Tests for UsageType enum."""

    def test_usage_type_values(self):
        """Test usage type enum values."""
        assert UsageType.INPUT_TOKENS.value == "input_tokens"
        assert UsageType.OUTPUT_TOKENS.value == "output_tokens"
        assert UsageType.AGENT_EXECUTIONS.value == "agent_executions"


class TestUsageRecord:
    """Tests for UsageRecord dataclass."""

    def test_record_creation(self):
        """Test creating a usage record."""
        record = UsageRecord(
            record_id="rec-1",
            tenant_id="tenant-1",
            user_id="user-1",
            usage_type=UsageType.INPUT_TOKENS,
            quantity=1000,
            model="gpt-4",
        )

        assert record.tenant_id == "tenant-1"
        assert record.usage_type == UsageType.INPUT_TOKENS
        assert record.quantity == 1000
        assert record.model == "gpt-4"

    def test_record_to_dict(self):
        """Test converting record to dictionary."""
        record = UsageRecord(
            record_id="rec-1",
            tenant_id="tenant-1",
            user_id=None,
            usage_type=UsageType.API_CALLS,
            quantity=1,
        )

        result = record.to_dict()

        assert result["record_id"] == "rec-1"
        assert result["usage_type"] == "api_calls"
        assert result["quantity"] == 1

    def test_record_from_dict(self):
        """Test creating record from dictionary."""
        data = {
            "record_id": "rec-2",
            "tenant_id": "tenant-2",
            "user_id": "user-2",
            "usage_type": "output_tokens",
            "quantity": 500,
            "model": "gpt-4o",
            "timestamp": "2025-01-01T12:00:00+00:00",
        }

        record = UsageRecord.from_dict(data)

        assert record.record_id == "rec-2"
        assert record.usage_type == UsageType.OUTPUT_TOKENS
        assert record.model == "gpt-4o"


class TestUsageTracker:
    """Tests for UsageTracker."""

    @pytest.fixture
    def tracker(self):
        """Create a usage tracker for testing."""
        return UsageTracker(max_records_in_memory=1000)

    def test_record_usage(self, tracker):
        """Test recording a usage event."""
        record = tracker.record_usage(
            tenant_id="tenant-1",
            usage_type=UsageType.API_CALLS,
            quantity=1,
            user_id="user-1",
        )

        assert record.tenant_id == "tenant-1"
        assert record.usage_type == UsageType.API_CALLS
        assert record.quantity == 1

    def test_record_tokens(self, tracker):
        """Test recording token usage."""
        records = tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=100,
            output_tokens=200,
            model="gpt-4",
            user_id="user-1",
        )

        assert len(records) == 3  # input, output, total

        input_rec = next(r for r in records if r.usage_type == UsageType.INPUT_TOKENS)
        assert input_rec.quantity == 100
        assert input_rec.model == "gpt-4"

        output_rec = next(r for r in records if r.usage_type == UsageType.OUTPUT_TOKENS)
        assert output_rec.quantity == 200

        total_rec = next(r for r in records if r.usage_type == UsageType.TOTAL_TOKENS)
        assert total_rec.quantity == 300

    def test_record_agent_execution(self, tracker):
        """Test recording agent execution."""
        record = tracker.record_agent_execution(
            tenant_id="tenant-1",
            agent_id="agent-1",
            user_id="user-1",
            metadata={"mission": "test"},
        )

        assert record.usage_type == UsageType.AGENT_EXECUTIONS
        assert record.quantity == 1
        assert record.agent_id == "agent-1"

    def test_record_tool_execution(self, tracker):
        """Test recording tool execution."""
        record = tracker.record_tool_execution(
            tenant_id="tenant-1",
            tool_name="python_tool",
            user_id="user-1",
        )

        assert record.usage_type == UsageType.TOOL_EXECUTIONS
        assert record.metadata["tool_name"] == "python_tool"

    def test_get_aggregation(self, tracker):
        """Test getting usage aggregation."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)

        # Record some usage
        tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=100,
            output_tokens=50,
            model="gpt-4",
        )
        tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=200,
            output_tokens=100,
            model="gpt-4o",
        )

        agg = tracker.get_aggregation(
            tenant_id="tenant-1",
            start_date=start,
            end_date=now,
        )

        assert agg.tenant_id == "tenant-1"
        assert UsageType.INPUT_TOKENS in agg.totals
        assert agg.totals[UsageType.INPUT_TOKENS] == 300
        assert agg.totals[UsageType.OUTPUT_TOKENS] == 150
        assert "gpt-4" in agg.by_model
        assert "gpt-4o" in agg.by_model

    def test_get_aggregation_by_user(self, tracker):
        """Test aggregation filtered by user."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)

        # Record for different users
        tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=100,
            output_tokens=50,
            model="gpt-4",
            user_id="user-1",
        )
        tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=200,
            output_tokens=100,
            model="gpt-4",
            user_id="user-2",
        )

        # Get aggregation for user-1 only
        agg = tracker.get_aggregation(
            tenant_id="tenant-1",
            start_date=start,
            end_date=now,
            user_id="user-1",
        )

        assert agg.user_id == "user-1"
        assert agg.totals[UsageType.INPUT_TOKENS] == 100
        assert agg.totals[UsageType.OUTPUT_TOKENS] == 50

    def test_get_daily_totals(self, tracker):
        """Test getting daily usage totals."""
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)

        # Record some usage
        tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=100,
            output_tokens=50,
            model="gpt-4",
        )

        daily = tracker.get_daily_totals(
            tenant_id="tenant-1",
            start_date=yesterday,
            end_date=today,
        )

        assert today in daily
        assert UsageType.INPUT_TOKENS in daily[today]
        assert daily[today][UsageType.INPUT_TOKENS] == 100

    def test_get_records(self, tracker):
        """Test getting raw records."""
        tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=100,
            output_tokens=50,
            model="gpt-4",
        )
        tracker.record_agent_execution(
            tenant_id="tenant-1",
            agent_id="agent-1",
        )

        records = tracker.get_records(
            tenant_id="tenant-1",
            usage_type=UsageType.INPUT_TOKENS,
        )

        assert len(records) == 1
        assert records[0].usage_type == UsageType.INPUT_TOKENS

    def test_clear_by_tenant(self, tracker):
        """Test clearing records by tenant."""
        tracker.record_usage(
            tenant_id="tenant-1",
            usage_type=UsageType.API_CALLS,
            quantity=1,
        )
        tracker.record_usage(
            tenant_id="tenant-2",
            usage_type=UsageType.API_CALLS,
            quantity=1,
        )

        cleared = tracker.clear(tenant_id="tenant-1")

        assert cleared == 1

        # tenant-1 should be empty
        records = tracker.get_records(tenant_id="tenant-1")
        assert len(records) == 0

        # tenant-2 should still have records
        records = tracker.get_records(tenant_id="tenant-2")
        assert len(records) == 1

    def test_clear_all(self, tracker):
        """Test clearing all records."""
        tracker.record_usage(
            tenant_id="tenant-1",
            usage_type=UsageType.API_CALLS,
            quantity=1,
        )
        tracker.record_usage(
            tenant_id="tenant-2",
            usage_type=UsageType.API_CALLS,
            quantity=1,
        )

        cleared = tracker.clear()

        assert cleared == 2
        assert len(tracker.get_records(tenant_id="tenant-1")) == 0
        assert len(tracker.get_records(tenant_id="tenant-2")) == 0

    def test_prune_old_records(self):
        """Test automatic pruning of old records."""
        tracker = UsageTracker(max_records_in_memory=5)

        # Add more records than max
        for i in range(10):
            tracker.record_usage(
                tenant_id="tenant-1",
                usage_type=UsageType.API_CALLS,
                quantity=1,
            )

        # Should have pruned to max
        records = tracker.get_records(tenant_id="tenant-1", limit=100)
        assert len(records) <= 5
