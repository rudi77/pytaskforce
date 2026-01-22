"""Cost calculation for usage-based billing.

This module provides cost calculation based on usage records and
configurable model pricing.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from taskforce.application.reporting.usage import (
    UsageType,
    UsageAggregation,
    UsageTracker,
)


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass
class ModelPricing:
    """Pricing configuration for a model.

    Attributes:
        model_name: Name of the model
        input_token_price: Price per 1K input tokens
        output_token_price: Price per 1K output tokens
        currency: Currency code (e.g., "USD")
        effective_date: When this pricing became effective
        notes: Optional pricing notes
    """

    model_name: str
    input_token_price: Decimal
    output_token_price: Decimal
    currency: str = "USD"
    effective_date: datetime = field(default_factory=_utcnow)
    notes: str = ""

    def calculate_input_cost(self, tokens: int) -> Decimal:
        """Calculate cost for input tokens.

        Args:
            tokens: Number of input tokens

        Returns:
            Cost in currency units
        """
        return (Decimal(tokens) / Decimal(1000)) * self.input_token_price

    def calculate_output_cost(self, tokens: int) -> Decimal:
        """Calculate cost for output tokens.

        Args:
            tokens: Number of output tokens

        Returns:
            Cost in currency units
        """
        return (Decimal(tokens) / Decimal(1000)) * self.output_token_price

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_name": self.model_name,
            "input_token_price": str(self.input_token_price),
            "output_token_price": str(self.output_token_price),
            "currency": self.currency,
            "effective_date": self.effective_date.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelPricing":
        """Create from dictionary."""
        return cls(
            model_name=data["model_name"],
            input_token_price=Decimal(data["input_token_price"]),
            output_token_price=Decimal(data["output_token_price"]),
            currency=data.get("currency", "USD"),
            effective_date=datetime.fromisoformat(data["effective_date"]),
            notes=data.get("notes", ""),
        )


@dataclass
class CostLineItem:
    """A single line item in a cost report.

    Attributes:
        description: Description of the charge
        usage_type: Type of usage
        quantity: Quantity used
        unit: Unit of measurement
        unit_price: Price per unit
        total: Total cost
        model: Optional model name
        agent_id: Optional agent ID
    """

    description: str
    usage_type: UsageType
    quantity: int
    unit: str
    unit_price: Decimal
    total: Decimal
    model: Optional[str] = None
    agent_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.description,
            "usage_type": self.usage_type.value,
            "quantity": self.quantity,
            "unit": self.unit,
            "unit_price": str(self.unit_price),
            "total": str(self.total),
            "model": self.model,
            "agent_id": self.agent_id,
        }


@dataclass
class CostReport:
    """Cost report for a billing period.

    Attributes:
        report_id: Unique report identifier
        tenant_id: Tenant ID
        period_start: Start of billing period
        period_end: End of billing period
        line_items: List of cost line items
        subtotal: Subtotal before adjustments
        adjustments: Any adjustments (discounts, credits)
        total: Final total
        currency: Currency code
        generated_at: When report was generated
        metadata: Additional metadata
    """

    report_id: str
    tenant_id: str
    period_start: datetime
    period_end: datetime
    line_items: List[CostLineItem] = field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    adjustments: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    currency: str = "USD"
    generated_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_line_item(self, item: CostLineItem) -> None:
        """Add a line item to the report.

        Args:
            item: Line item to add
        """
        self.line_items.append(item)
        self.subtotal += item.total
        self.total = self.subtotal + self.adjustments

    def apply_adjustment(self, amount: Decimal, reason: str) -> None:
        """Apply an adjustment (discount or credit).

        Args:
            amount: Adjustment amount (negative for discount)
            reason: Reason for adjustment
        """
        self.adjustments += amount
        self.total = self.subtotal + self.adjustments
        if "adjustments_detail" not in self.metadata:
            self.metadata["adjustments_detail"] = []
        self.metadata["adjustments_detail"].append({
            "amount": str(amount),
            "reason": reason,
        })

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "tenant_id": self.tenant_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "line_items": [item.to_dict() for item in self.line_items],
            "subtotal": str(self.subtotal),
            "adjustments": str(self.adjustments),
            "total": str(self.total),
            "currency": self.currency,
            "generated_at": self.generated_at.isoformat(),
            "metadata": self.metadata,
        }


class CostCalculator:
    """Calculates costs from usage based on pricing.

    This class manages model pricing and generates cost reports
    from usage aggregations.
    """

    # Default pricing for common models (per 1K tokens)
    DEFAULT_PRICING = {
        "gpt-4": ModelPricing(
            model_name="gpt-4",
            input_token_price=Decimal("0.03"),
            output_token_price=Decimal("0.06"),
        ),
        "gpt-4-turbo": ModelPricing(
            model_name="gpt-4-turbo",
            input_token_price=Decimal("0.01"),
            output_token_price=Decimal("0.03"),
        ),
        "gpt-4o": ModelPricing(
            model_name="gpt-4o",
            input_token_price=Decimal("0.005"),
            output_token_price=Decimal("0.015"),
        ),
        "gpt-4o-mini": ModelPricing(
            model_name="gpt-4o-mini",
            input_token_price=Decimal("0.00015"),
            output_token_price=Decimal("0.0006"),
        ),
        "gpt-3.5-turbo": ModelPricing(
            model_name="gpt-3.5-turbo",
            input_token_price=Decimal("0.0005"),
            output_token_price=Decimal("0.0015"),
        ),
        "claude-3-opus": ModelPricing(
            model_name="claude-3-opus",
            input_token_price=Decimal("0.015"),
            output_token_price=Decimal("0.075"),
        ),
        "claude-3-sonnet": ModelPricing(
            model_name="claude-3-sonnet",
            input_token_price=Decimal("0.003"),
            output_token_price=Decimal("0.015"),
        ),
        "claude-3-haiku": ModelPricing(
            model_name="claude-3-haiku",
            input_token_price=Decimal("0.00025"),
            output_token_price=Decimal("0.00125"),
        ),
    }

    def __init__(
        self,
        pricing: Optional[Dict[str, ModelPricing]] = None,
        default_currency: str = "USD",
    ):
        """Initialize the cost calculator.

        Args:
            pricing: Optional pricing configuration
            default_currency: Default currency for reports
        """
        self._pricing: Dict[str, ModelPricing] = {}
        self._pricing.update(self.DEFAULT_PRICING)
        if pricing:
            self._pricing.update(pricing)
        self._default_currency = default_currency

    def set_pricing(self, model_name: str, pricing: ModelPricing) -> None:
        """Set pricing for a model.

        Args:
            model_name: Model name
            pricing: Pricing configuration
        """
        self._pricing[model_name] = pricing

    def get_pricing(self, model_name: str) -> Optional[ModelPricing]:
        """Get pricing for a model.

        Args:
            model_name: Model name

        Returns:
            ModelPricing if found, None otherwise
        """
        return self._pricing.get(model_name)

    def calculate_token_cost(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Optional[Decimal]:
        """Calculate cost for token usage.

        Args:
            model_name: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Total cost, or None if pricing not found
        """
        pricing = self._pricing.get(model_name)
        if not pricing:
            return None

        input_cost = pricing.calculate_input_cost(input_tokens)
        output_cost = pricing.calculate_output_cost(output_tokens)
        return input_cost + output_cost

    def generate_report(
        self,
        aggregation: UsageAggregation,
        report_id: Optional[str] = None,
    ) -> CostReport:
        """Generate a cost report from usage aggregation.

        Args:
            aggregation: Usage aggregation data
            report_id: Optional report ID

        Returns:
            Cost report with line items
        """
        import uuid

        report = CostReport(
            report_id=report_id or str(uuid.uuid4()),
            tenant_id=aggregation.tenant_id,
            period_start=aggregation.period_start,
            period_end=aggregation.period_end,
            currency=self._default_currency,
        )

        # Add line items for each model's token usage
        for model_name, usage in aggregation.by_model.items():
            pricing = self._pricing.get(model_name)
            if not pricing:
                # Use unknown model pricing
                pricing = ModelPricing(
                    model_name=model_name,
                    input_token_price=Decimal("0.001"),
                    output_token_price=Decimal("0.002"),
                )

            input_tokens = usage.get(UsageType.INPUT_TOKENS, 0)
            output_tokens = usage.get(UsageType.OUTPUT_TOKENS, 0)

            if input_tokens > 0:
                input_cost = pricing.calculate_input_cost(input_tokens)
                report.add_line_item(CostLineItem(
                    description=f"{model_name} - Input Tokens",
                    usage_type=UsageType.INPUT_TOKENS,
                    quantity=input_tokens,
                    unit="1K tokens",
                    unit_price=pricing.input_token_price,
                    total=input_cost,
                    model=model_name,
                ))

            if output_tokens > 0:
                output_cost = pricing.calculate_output_cost(output_tokens)
                report.add_line_item(CostLineItem(
                    description=f"{model_name} - Output Tokens",
                    usage_type=UsageType.OUTPUT_TOKENS,
                    quantity=output_tokens,
                    unit="1K tokens",
                    unit_price=pricing.output_token_price,
                    total=output_cost,
                    model=model_name,
                ))

        # Add summary metadata
        report.metadata["total_input_tokens"] = aggregation.totals.get(
            UsageType.INPUT_TOKENS, 0
        )
        report.metadata["total_output_tokens"] = aggregation.totals.get(
            UsageType.OUTPUT_TOKENS, 0
        )
        report.metadata["total_api_calls"] = aggregation.totals.get(
            UsageType.API_CALLS, 0
        )
        report.metadata["total_agent_executions"] = aggregation.totals.get(
            UsageType.AGENT_EXECUTIONS, 0
        )
        report.metadata["total_tool_executions"] = aggregation.totals.get(
            UsageType.TOOL_EXECUTIONS, 0
        )

        return report

    def generate_report_from_tracker(
        self,
        tracker: UsageTracker,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None,
    ) -> CostReport:
        """Generate a cost report directly from a usage tracker.

        Args:
            tracker: Usage tracker instance
            tenant_id: Tenant ID
            start_date: Start of period
            end_date: End of period
            user_id: Optional user filter

        Returns:
            Cost report
        """
        aggregation = tracker.get_aggregation(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
        )
        return self.generate_report(aggregation)

    def load_pricing_from_config(self, config: Dict[str, Any]) -> None:
        """Load pricing configuration from a dictionary.

        Args:
            config: Pricing configuration dictionary
        """
        for model_name, pricing_data in config.get("models", {}).items():
            self._pricing[model_name] = ModelPricing(
                model_name=model_name,
                input_token_price=Decimal(str(pricing_data.get("input_price", "0.001"))),
                output_token_price=Decimal(str(pricing_data.get("output_price", "0.002"))),
                currency=pricing_data.get("currency", self._default_currency),
                notes=pricing_data.get("notes", ""),
            )
