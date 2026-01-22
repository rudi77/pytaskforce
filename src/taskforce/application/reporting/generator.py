"""Report generation for usage, cost, and compliance.

This module provides report generation in various formats
for billing integration and analytics.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone, timedelta
from enum import Enum
from io import StringIO
import json
import csv

from taskforce.application.reporting.usage import (
    UsageType,
    UsageTracker,
    UsageAggregation,
)
from taskforce.application.reporting.cost import (
    CostCalculator,
    CostReport,
)


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ReportFormat(Enum):
    """Supported report output formats."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportPeriod(Enum):
    """Standard report periods."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


@dataclass
class ReportMetadata:
    """Metadata for a generated report.

    Attributes:
        report_type: Type of report
        format: Output format
        period: Report period
        start_date: Start of period
        end_date: End of period
        tenant_id: Tenant ID
        user_id: Optional user filter
        generated_at: When report was generated
        generated_by: Who/what generated the report
    """

    report_type: str
    format: ReportFormat
    period: ReportPeriod
    start_date: datetime
    end_date: datetime
    tenant_id: str
    user_id: Optional[str] = None
    generated_at: datetime = field(default_factory=_utcnow)
    generated_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_type": self.report_type,
            "format": self.format.value,
            "period": self.period.value,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "generated_at": self.generated_at.isoformat(),
            "generated_by": self.generated_by,
        }


@dataclass
class GeneratedReport:
    """A generated report with content.

    Attributes:
        metadata: Report metadata
        content: Report content (format depends on output format)
        filename: Suggested filename
    """

    metadata: ReportMetadata
    content: str
    filename: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "content": self.content,
            "filename": self.filename,
        }


class ReportGenerator:
    """Generates reports from usage and cost data.

    This class provides methods for generating reports in various
    formats for billing integration and analytics.
    """

    def __init__(
        self,
        usage_tracker: UsageTracker,
        cost_calculator: CostCalculator,
    ):
        """Initialize the report generator.

        Args:
            usage_tracker: Usage tracker instance
            cost_calculator: Cost calculator instance
        """
        self._tracker = usage_tracker
        self._calculator = cost_calculator

    def generate_usage_report(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        format: ReportFormat = ReportFormat.JSON,
        user_id: Optional[str] = None,
    ) -> GeneratedReport:
        """Generate a usage report.

        Args:
            tenant_id: Tenant ID
            start_date: Start of period
            end_date: End of period
            format: Output format
            user_id: Optional user filter

        Returns:
            Generated report
        """
        aggregation = self._tracker.get_aggregation(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
        )

        metadata = ReportMetadata(
            report_type="usage",
            format=format,
            period=self._determine_period(start_date, end_date),
            start_date=start_date,
            end_date=end_date,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if format == ReportFormat.JSON:
            content = self._format_usage_json(aggregation)
        elif format == ReportFormat.CSV:
            content = self._format_usage_csv(aggregation)
        elif format == ReportFormat.MARKDOWN:
            content = self._format_usage_markdown(aggregation)
        else:
            content = self._format_usage_json(aggregation)

        filename = self._generate_filename("usage", tenant_id, start_date, end_date, format)

        return GeneratedReport(
            metadata=metadata,
            content=content,
            filename=filename,
        )

    def generate_cost_report(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        format: ReportFormat = ReportFormat.JSON,
        user_id: Optional[str] = None,
    ) -> GeneratedReport:
        """Generate a cost report.

        Args:
            tenant_id: Tenant ID
            start_date: Start of period
            end_date: End of period
            format: Output format
            user_id: Optional user filter

        Returns:
            Generated report
        """
        cost_report = self._calculator.generate_report_from_tracker(
            tracker=self._tracker,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
        )

        metadata = ReportMetadata(
            report_type="cost",
            format=format,
            period=self._determine_period(start_date, end_date),
            start_date=start_date,
            end_date=end_date,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if format == ReportFormat.JSON:
            content = self._format_cost_json(cost_report)
        elif format == ReportFormat.CSV:
            content = self._format_cost_csv(cost_report)
        elif format == ReportFormat.MARKDOWN:
            content = self._format_cost_markdown(cost_report)
        else:
            content = self._format_cost_json(cost_report)

        filename = self._generate_filename("cost", tenant_id, start_date, end_date, format)

        return GeneratedReport(
            metadata=metadata,
            content=content,
            filename=filename,
        )

    def generate_billing_export(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Generate a billing export for integration.

        Args:
            tenant_id: Tenant ID
            start_date: Start of period
            end_date: End of period

        Returns:
            Billing data dictionary for API integration
        """
        cost_report = self._calculator.generate_report_from_tracker(
            tracker=self._tracker,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            "tenant_id": tenant_id,
            "billing_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_amount": str(cost_report.total),
            "currency": cost_report.currency,
            "line_items": [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "amount": str(item.total),
                }
                for item in cost_report.line_items
            ],
            "adjustments": str(cost_report.adjustments),
            "generated_at": _utcnow().isoformat(),
        }

    def _determine_period(self, start: datetime, end: datetime) -> ReportPeriod:
        """Determine the report period type."""
        delta = end - start
        if delta.days <= 1:
            return ReportPeriod.DAILY
        elif delta.days <= 7:
            return ReportPeriod.WEEKLY
        elif delta.days <= 31:
            return ReportPeriod.MONTHLY
        elif delta.days <= 92:
            return ReportPeriod.QUARTERLY
        elif delta.days <= 366:
            return ReportPeriod.YEARLY
        return ReportPeriod.CUSTOM

    def _generate_filename(
        self,
        report_type: str,
        tenant_id: str,
        start: datetime,
        end: datetime,
        format: ReportFormat,
    ) -> str:
        """Generate a filename for the report."""
        ext = format.value
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        return f"{report_type}_{tenant_id}_{start_str}_{end_str}.{ext}"

    def _format_usage_json(self, aggregation: UsageAggregation) -> str:
        """Format usage aggregation as JSON."""
        return json.dumps(aggregation.to_dict(), indent=2)

    def _format_usage_csv(self, aggregation: UsageAggregation) -> str:
        """Format usage aggregation as CSV."""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "tenant_id",
            "user_id",
            "period_start",
            "period_end",
            "usage_type",
            "quantity",
            "model",
            "agent_id",
        ])

        # Totals
        for usage_type, quantity in aggregation.totals.items():
            writer.writerow([
                aggregation.tenant_id,
                aggregation.user_id or "",
                aggregation.period_start.isoformat(),
                aggregation.period_end.isoformat(),
                usage_type.value,
                quantity,
                "",
                "",
            ])

        # By model
        for model, usage in aggregation.by_model.items():
            for usage_type, quantity in usage.items():
                writer.writerow([
                    aggregation.tenant_id,
                    aggregation.user_id or "",
                    aggregation.period_start.isoformat(),
                    aggregation.period_end.isoformat(),
                    usage_type.value,
                    quantity,
                    model,
                    "",
                ])

        return output.getvalue()

    def _format_usage_markdown(self, aggregation: UsageAggregation) -> str:
        """Format usage aggregation as Markdown."""
        lines = [
            f"# Usage Report",
            f"",
            f"**Tenant:** {aggregation.tenant_id}",
        ]

        if aggregation.user_id:
            lines.append(f"**User:** {aggregation.user_id}")

        lines.extend([
            f"**Period:** {aggregation.period_start.strftime('%Y-%m-%d')} to {aggregation.period_end.strftime('%Y-%m-%d')}",
            f"**Records:** {aggregation.record_count}",
            f"",
            "## Summary",
            "",
            "| Usage Type | Quantity |",
            "|------------|----------|",
        ])

        for usage_type, quantity in aggregation.totals.items():
            lines.append(f"| {usage_type.value} | {quantity:,} |")

        if aggregation.by_model:
            lines.extend([
                "",
                "## By Model",
                "",
            ])

            for model, usage in aggregation.by_model.items():
                lines.append(f"### {model}")
                lines.append("")
                lines.append("| Usage Type | Quantity |")
                lines.append("|------------|----------|")
                for usage_type, quantity in usage.items():
                    lines.append(f"| {usage_type.value} | {quantity:,} |")
                lines.append("")

        return "\n".join(lines)

    def _format_cost_json(self, report: CostReport) -> str:
        """Format cost report as JSON."""
        return json.dumps(report.to_dict(), indent=2)

    def _format_cost_csv(self, report: CostReport) -> str:
        """Format cost report as CSV."""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "description",
            "usage_type",
            "quantity",
            "unit",
            "unit_price",
            "total",
            "model",
        ])

        # Line items
        for item in report.line_items:
            writer.writerow([
                item.description,
                item.usage_type.value,
                item.quantity,
                item.unit,
                str(item.unit_price),
                str(item.total),
                item.model or "",
            ])

        # Totals row
        writer.writerow([
            "SUBTOTAL",
            "",
            "",
            "",
            "",
            str(report.subtotal),
            "",
        ])
        writer.writerow([
            "ADJUSTMENTS",
            "",
            "",
            "",
            "",
            str(report.adjustments),
            "",
        ])
        writer.writerow([
            "TOTAL",
            "",
            "",
            "",
            "",
            str(report.total),
            "",
        ])

        return output.getvalue()

    def _format_cost_markdown(self, report: CostReport) -> str:
        """Format cost report as Markdown."""
        lines = [
            f"# Cost Report",
            f"",
            f"**Report ID:** {report.report_id}",
            f"**Tenant:** {report.tenant_id}",
            f"**Period:** {report.period_start.strftime('%Y-%m-%d')} to {report.period_end.strftime('%Y-%m-%d')}",
            f"**Currency:** {report.currency}",
            f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"",
            "## Line Items",
            "",
            "| Description | Quantity | Unit | Unit Price | Total |",
            "|-------------|----------|------|------------|-------|",
        ]

        for item in report.line_items:
            lines.append(
                f"| {item.description} | {item.quantity:,} | {item.unit} | "
                f"${item.unit_price:.6f} | ${item.total:.4f} |"
            )

        lines.extend([
            "",
            "## Summary",
            "",
            f"| | Amount |",
            f"|---|------|",
            f"| Subtotal | ${report.subtotal:.4f} |",
            f"| Adjustments | ${report.adjustments:.4f} |",
            f"| **Total** | **${report.total:.4f}** |",
        ])

        # Add metadata summary
        if report.metadata:
            lines.extend([
                "",
                "## Usage Summary",
                "",
            ])
            if "total_input_tokens" in report.metadata:
                lines.append(f"- Total Input Tokens: {report.metadata['total_input_tokens']:,}")
            if "total_output_tokens" in report.metadata:
                lines.append(f"- Total Output Tokens: {report.metadata['total_output_tokens']:,}")
            if "total_agent_executions" in report.metadata:
                lines.append(f"- Agent Executions: {report.metadata['total_agent_executions']:,}")
            if "total_tool_executions" in report.metadata:
                lines.append(f"- Tool Executions: {report.metadata['total_tool_executions']:,}")

        return "\n".join(lines)


def get_period_dates(period: ReportPeriod, reference_date: Optional[datetime] = None) -> tuple:
    """Get start and end dates for a standard period.

    Args:
        period: Report period type
        reference_date: Reference date (defaults to now)

    Returns:
        Tuple of (start_date, end_date)
    """
    now = reference_date or _utcnow()

    if period == ReportPeriod.DAILY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
    elif period == ReportPeriod.WEEKLY:
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7) - timedelta(microseconds=1)
    elif period == ReportPeriod.MONTHLY:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=now.year + 1, month=1)
        else:
            end = start.replace(month=now.month + 1)
        end = end - timedelta(microseconds=1)
    elif period == ReportPeriod.QUARTERLY:
        quarter = (now.month - 1) // 3
        start = now.replace(month=quarter * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        if quarter == 3:
            end = start.replace(year=now.year + 1, month=1)
        else:
            end = start.replace(month=(quarter + 1) * 3 + 1)
        end = end - timedelta(microseconds=1)
    elif period == ReportPeriod.YEARLY:
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=now.year + 1) - timedelta(microseconds=1)
    else:
        # CUSTOM - use reference date as is
        start = now
        end = now

    return start, end
