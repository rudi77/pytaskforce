"""Tests for cost calculation."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from taskforce.application.reporting.usage import (
    UsageType,
    UsageAggregation,
    UsageTracker,
)
from taskforce.application.reporting.cost import (
    ModelPricing,
    CostLineItem,
    CostReport,
    CostCalculator,
)


class TestModelPricing:
    """Tests for ModelPricing dataclass."""

    def test_pricing_creation(self):
        """Test creating model pricing."""
        pricing = ModelPricing(
            model_name="test-model",
            input_token_price=Decimal("0.01"),
            output_token_price=Decimal("0.02"),
        )

        assert pricing.model_name == "test-model"
        assert pricing.input_token_price == Decimal("0.01")
        assert pricing.output_token_price == Decimal("0.02")
        assert pricing.currency == "USD"

    def test_calculate_input_cost(self):
        """Test calculating input token cost."""
        pricing = ModelPricing(
            model_name="test-model",
            input_token_price=Decimal("0.01"),  # per 1K tokens
            output_token_price=Decimal("0.02"),
        )

        cost = pricing.calculate_input_cost(5000)  # 5K tokens

        assert cost == Decimal("0.05")

    def test_calculate_output_cost(self):
        """Test calculating output token cost."""
        pricing = ModelPricing(
            model_name="test-model",
            input_token_price=Decimal("0.01"),
            output_token_price=Decimal("0.03"),  # per 1K tokens
        )

        cost = pricing.calculate_output_cost(2000)  # 2K tokens

        assert cost == Decimal("0.06")

    def test_pricing_to_dict(self):
        """Test converting pricing to dictionary."""
        pricing = ModelPricing(
            model_name="gpt-4",
            input_token_price=Decimal("0.03"),
            output_token_price=Decimal("0.06"),
        )

        result = pricing.to_dict()

        assert result["model_name"] == "gpt-4"
        assert result["input_token_price"] == "0.03"
        assert result["output_token_price"] == "0.06"

    def test_pricing_from_dict(self):
        """Test creating pricing from dictionary."""
        data = {
            "model_name": "claude-3",
            "input_token_price": "0.015",
            "output_token_price": "0.075",
            "currency": "USD",
            "effective_date": "2025-01-01T00:00:00+00:00",
        }

        pricing = ModelPricing.from_dict(data)

        assert pricing.model_name == "claude-3"
        assert pricing.input_token_price == Decimal("0.015")
        assert pricing.output_token_price == Decimal("0.075")


class TestCostLineItem:
    """Tests for CostLineItem dataclass."""

    def test_line_item_creation(self):
        """Test creating a cost line item."""
        item = CostLineItem(
            description="GPT-4 Input Tokens",
            usage_type=UsageType.INPUT_TOKENS,
            quantity=10000,
            unit="1K tokens",
            unit_price=Decimal("0.03"),
            total=Decimal("0.30"),
            model="gpt-4",
        )

        assert item.quantity == 10000
        assert item.total == Decimal("0.30")

    def test_line_item_to_dict(self):
        """Test converting line item to dictionary."""
        item = CostLineItem(
            description="Test",
            usage_type=UsageType.OUTPUT_TOKENS,
            quantity=5000,
            unit="1K tokens",
            unit_price=Decimal("0.06"),
            total=Decimal("0.30"),
        )

        result = item.to_dict()

        assert result["description"] == "Test"
        assert result["total"] == "0.30"


class TestCostReport:
    """Tests for CostReport dataclass."""

    @pytest.fixture
    def report(self):
        """Create a cost report for testing."""
        return CostReport(
            report_id="report-1",
            tenant_id="tenant-1",
            period_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2025, 1, 31, tzinfo=timezone.utc),
        )

    def test_add_line_item(self, report):
        """Test adding a line item to report."""
        item = CostLineItem(
            description="GPT-4 Tokens",
            usage_type=UsageType.TOTAL_TOKENS,
            quantity=10000,
            unit="1K tokens",
            unit_price=Decimal("0.05"),
            total=Decimal("0.50"),
        )

        report.add_line_item(item)

        assert len(report.line_items) == 1
        assert report.subtotal == Decimal("0.50")
        assert report.total == Decimal("0.50")

    def test_add_multiple_line_items(self, report):
        """Test adding multiple line items."""
        item1 = CostLineItem(
            description="Input",
            usage_type=UsageType.INPUT_TOKENS,
            quantity=5000,
            unit="1K tokens",
            unit_price=Decimal("0.01"),
            total=Decimal("0.05"),
        )
        item2 = CostLineItem(
            description="Output",
            usage_type=UsageType.OUTPUT_TOKENS,
            quantity=2000,
            unit="1K tokens",
            unit_price=Decimal("0.02"),
            total=Decimal("0.04"),
        )

        report.add_line_item(item1)
        report.add_line_item(item2)

        assert len(report.line_items) == 2
        assert report.subtotal == Decimal("0.09")

    def test_apply_adjustment(self, report):
        """Test applying an adjustment."""
        item = CostLineItem(
            description="Tokens",
            usage_type=UsageType.TOTAL_TOKENS,
            quantity=10000,
            unit="1K tokens",
            unit_price=Decimal("0.05"),
            total=Decimal("0.50"),
        )
        report.add_line_item(item)

        # Apply 10% discount
        report.apply_adjustment(Decimal("-0.05"), "10% volume discount")

        assert report.adjustments == Decimal("-0.05")
        assert report.total == Decimal("0.45")
        assert "adjustments_detail" in report.metadata

    def test_report_to_dict(self, report):
        """Test converting report to dictionary."""
        item = CostLineItem(
            description="Test",
            usage_type=UsageType.TOTAL_TOKENS,
            quantity=1000,
            unit="1K tokens",
            unit_price=Decimal("0.01"),
            total=Decimal("0.01"),
        )
        report.add_line_item(item)

        result = report.to_dict()

        assert result["report_id"] == "report-1"
        assert result["tenant_id"] == "tenant-1"
        assert len(result["line_items"]) == 1
        assert result["total"] == "0.01"


class TestCostCalculator:
    """Tests for CostCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create a cost calculator for testing."""
        return CostCalculator()

    def test_default_pricing_loaded(self, calculator):
        """Test that default pricing is loaded."""
        gpt4_pricing = calculator.get_pricing("gpt-4")
        assert gpt4_pricing is not None
        assert gpt4_pricing.model_name == "gpt-4"

    def test_set_custom_pricing(self, calculator):
        """Test setting custom pricing."""
        pricing = ModelPricing(
            model_name="custom-model",
            input_token_price=Decimal("0.001"),
            output_token_price=Decimal("0.002"),
        )

        calculator.set_pricing("custom-model", pricing)

        retrieved = calculator.get_pricing("custom-model")
        assert retrieved is not None
        assert retrieved.input_token_price == Decimal("0.001")

    def test_calculate_token_cost(self, calculator):
        """Test calculating token cost."""
        cost = calculator.calculate_token_cost(
            model_name="gpt-4",
            input_tokens=1000,
            output_tokens=500,
        )

        # gpt-4: $0.03/1K input, $0.06/1K output
        expected = Decimal("0.03") + Decimal("0.03")  # 1K input + 0.5K output
        assert cost == expected

    def test_calculate_token_cost_unknown_model(self, calculator):
        """Test token cost for unknown model returns None."""
        cost = calculator.calculate_token_cost(
            model_name="unknown-model",
            input_tokens=1000,
            output_tokens=500,
        )

        assert cost is None

    def test_generate_report(self, calculator):
        """Test generating cost report from aggregation."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        aggregation = UsageAggregation(
            tenant_id="tenant-1",
            user_id=None,
            period_start=start,
            period_end=now,
            record_count=100,
            by_model={
                "gpt-4": {
                    UsageType.INPUT_TOKENS: 10000,
                    UsageType.OUTPUT_TOKENS: 5000,
                },
            },
            totals={
                UsageType.INPUT_TOKENS: 10000,
                UsageType.OUTPUT_TOKENS: 5000,
                UsageType.TOTAL_TOKENS: 15000,
            },
        )

        report = calculator.generate_report(aggregation)

        assert report.tenant_id == "tenant-1"
        assert len(report.line_items) == 2  # input and output
        assert report.total > Decimal("0")

    def test_generate_report_from_tracker(self, calculator):
        """Test generating report directly from tracker."""
        tracker = UsageTracker()
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)

        # Add usage
        tracker.record_tokens(
            tenant_id="tenant-1",
            input_tokens=5000,
            output_tokens=2500,
            model="gpt-4",
        )

        report = calculator.generate_report_from_tracker(
            tracker=tracker,
            tenant_id="tenant-1",
            start_date=start,
            end_date=now,
        )

        assert report.tenant_id == "tenant-1"
        assert len(report.line_items) >= 2

    def test_generate_report_unknown_model_uses_default(self, calculator):
        """Test that unknown models use default pricing."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=30)

        aggregation = UsageAggregation(
            tenant_id="tenant-1",
            user_id=None,
            period_start=start,
            period_end=now,
            by_model={
                "unknown-new-model": {
                    UsageType.INPUT_TOKENS: 1000,
                    UsageType.OUTPUT_TOKENS: 500,
                },
            },
            totals={
                UsageType.INPUT_TOKENS: 1000,
                UsageType.OUTPUT_TOKENS: 500,
            },
        )

        report = calculator.generate_report(aggregation)

        # Should still generate line items with default pricing
        assert len(report.line_items) == 2
        assert report.total > Decimal("0")

    def test_load_pricing_from_config(self, calculator):
        """Test loading pricing from config dictionary."""
        config = {
            "models": {
                "custom-gpt": {
                    "input_price": "0.005",
                    "output_price": "0.010",
                    "currency": "USD",
                    "notes": "Custom pricing",
                },
            },
        }

        calculator.load_pricing_from_config(config)

        pricing = calculator.get_pricing("custom-gpt")
        assert pricing is not None
        assert pricing.input_token_price == Decimal("0.005")
        assert pricing.output_token_price == Decimal("0.010")
