"""Metrics collection for enterprise observability.

This module provides metrics collection for SLA monitoring,
usage tracking, and operational dashboards.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone, timedelta
from enum import Enum
from collections import defaultdict
import threading
import time
import structlog


logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class MetricType(Enum):
    """Types of metrics that can be collected."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class Metric:
    """A single metric data point.

    Attributes:
        name: Metric name
        type: Type of metric
        value: Current value
        labels: Dimension labels
        timestamp: When this metric was recorded
        unit: Unit of measurement
    """

    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    unit: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat(),
            "unit": self.unit,
        }

    def to_prometheus(self) -> str:
        """Format as Prometheus metric line."""
        labels_str = ""
        if self.labels:
            label_parts = [f'{k}="{v}"' for k, v in self.labels.items()]
            labels_str = "{" + ",".join(label_parts) + "}"
        return f"{self.name}{labels_str} {self.value}"


@dataclass
class HistogramBucket:
    """A histogram bucket for latency tracking."""

    le: float  # Less than or equal
    count: int = 0


@dataclass
class HistogramMetric:
    """Histogram metric for latency distribution.

    Attributes:
        name: Metric name
        labels: Dimension labels
        buckets: List of buckets
        sum: Sum of all observations
        count: Total observation count
    """

    name: str
    labels: Dict[str, str] = field(default_factory=dict)
    buckets: List[HistogramBucket] = field(default_factory=list)
    sum: float = 0.0
    count: int = 0

    def __post_init__(self):
        if not self.buckets:
            # Default latency buckets in seconds
            default_les = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
            self.buckets = [HistogramBucket(le=le) for le in default_les]
            self.buckets.append(HistogramBucket(le=float("inf")))

    def observe(self, value: float) -> None:
        """Record an observation.

        Args:
            value: Value to observe
        """
        self.sum += value
        self.count += 1
        for bucket in self.buckets:
            if value <= bucket.le:
                bucket.count += 1

    def get_percentile(self, p: float) -> float:
        """Get approximate percentile from histogram.

        Args:
            p: Percentile (0-100)

        Returns:
            Approximate percentile value
        """
        target = self.count * (p / 100.0)
        for i, bucket in enumerate(self.buckets):
            if bucket.count >= target:
                if i == 0:
                    return bucket.le
                prev = self.buckets[i - 1]
                # Linear interpolation
                if bucket.count == prev.count:
                    return bucket.le
                ratio = (target - prev.count) / (bucket.count - prev.count)
                return prev.le + ratio * (bucket.le - prev.le)
        return self.buckets[-1].le


class MetricsCollector:
    """Collects and manages application metrics.

    Thread-safe collector for various metric types supporting
    labels, histograms, and Prometheus export.
    """

    def __init__(self, prefix: str = "taskforce"):
        """Initialize the metrics collector.

        Args:
            prefix: Prefix for all metric names
        """
        self.prefix = prefix
        self._lock = threading.Lock()
        self._counters: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: Dict[str, Dict[str, HistogramMetric]] = defaultdict(dict)

        # Built-in metrics
        self._setup_builtin_metrics()

    def _setup_builtin_metrics(self) -> None:
        """Set up built-in metrics."""
        # These are initialized lazily on first use
        pass

    def _label_key(self, labels: Dict[str, str]) -> str:
        """Create a unique key from labels."""
        if not labels:
            return ""
        sorted_items = sorted(labels.items())
        return "|".join(f"{k}={v}" for k, v in sorted_items)

    def inc(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter.

        Args:
            name: Counter name
            value: Value to add
            labels: Optional labels
        """
        full_name = f"{self.prefix}_{name}"
        key = self._label_key(labels or {})
        with self._lock:
            self._counters[full_name][key] += value

    def set(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge value.

        Args:
            name: Gauge name
            value: Value to set
            labels: Optional labels
        """
        full_name = f"{self.prefix}_{name}"
        key = self._label_key(labels or {})
        with self._lock:
            self._gauges[full_name][key] = value

    def observe(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a histogram observation.

        Args:
            name: Histogram name
            value: Value to observe
            labels: Optional labels
        """
        full_name = f"{self.prefix}_{name}"
        key = self._label_key(labels or {})
        with self._lock:
            if key not in self._histograms[full_name]:
                self._histograms[full_name][key] = HistogramMetric(
                    name=full_name,
                    labels=labels or {},
                )
            self._histograms[full_name][key].observe(value)

    def time(self, name: str, labels: Optional[Dict[str, str]] = None) -> "Timer":
        """Create a timer context manager for measuring duration.

        Args:
            name: Metric name for the duration
            labels: Optional labels

        Returns:
            Timer context manager
        """
        return Timer(self, name, labels)

    # SLA-specific metrics

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_seconds: float,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Record an API request for SLA tracking.

        Args:
            endpoint: API endpoint
            method: HTTP method
            status_code: Response status code
            duration_seconds: Request duration
            tenant_id: Optional tenant ID
        """
        labels = {
            "endpoint": endpoint,
            "method": method,
            "status": str(status_code),
        }
        if tenant_id:
            labels["tenant_id"] = tenant_id

        self.inc("http_requests_total", labels=labels)
        self.observe("http_request_duration_seconds", duration_seconds, labels=labels)

        if status_code >= 500:
            self.inc("http_errors_total", labels=labels)

    def record_agent_execution(
        self,
        agent_id: str,
        success: bool,
        duration_seconds: float,
        steps: int,
        tokens_used: int,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Record an agent execution for metrics.

        Args:
            agent_id: Agent identifier
            success: Whether execution succeeded
            duration_seconds: Total execution time
            steps: Number of reasoning steps
            tokens_used: Total tokens consumed
            tenant_id: Optional tenant ID
        """
        labels = {"agent_id": agent_id}
        if tenant_id:
            labels["tenant_id"] = tenant_id

        self.inc("agent_executions_total", labels={**labels, "success": str(success).lower()})
        self.observe("agent_execution_duration_seconds", duration_seconds, labels=labels)
        self.observe("agent_execution_steps", float(steps), labels=labels)
        self.inc("agent_tokens_total", float(tokens_used), labels=labels)

    def record_tool_execution(
        self,
        tool_name: str,
        success: bool,
        duration_seconds: float,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Record a tool execution.

        Args:
            tool_name: Tool name
            success: Whether execution succeeded
            duration_seconds: Execution duration
            tenant_id: Optional tenant ID
        """
        labels = {"tool": tool_name}
        if tenant_id:
            labels["tenant_id"] = tenant_id

        self.inc("tool_executions_total", labels={**labels, "success": str(success).lower()})
        self.observe("tool_execution_duration_seconds", duration_seconds, labels=labels)

    # Export methods

    def get_all_metrics(self) -> List[Metric]:
        """Get all current metric values.

        Returns:
            List of all metrics
        """
        metrics = []
        now = _utcnow()

        with self._lock:
            # Counters
            for name, values in self._counters.items():
                for key, value in values.items():
                    labels = self._parse_label_key(key)
                    metrics.append(Metric(
                        name=name,
                        type=MetricType.COUNTER,
                        value=value,
                        labels=labels,
                        timestamp=now,
                    ))

            # Gauges
            for name, values in self._gauges.items():
                for key, value in values.items():
                    labels = self._parse_label_key(key)
                    metrics.append(Metric(
                        name=name,
                        type=MetricType.GAUGE,
                        value=value,
                        labels=labels,
                        timestamp=now,
                    ))

        return metrics

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        lines = []

        with self._lock:
            # Counters
            for name, values in self._counters.items():
                lines.append(f"# TYPE {name} counter")
                for key, value in values.items():
                    labels = self._parse_label_key(key)
                    labels_str = self._format_labels(labels)
                    lines.append(f"{name}{labels_str} {value}")

            # Gauges
            for name, values in self._gauges.items():
                lines.append(f"# TYPE {name} gauge")
                for key, value in values.items():
                    labels = self._parse_label_key(key)
                    labels_str = self._format_labels(labels)
                    lines.append(f"{name}{labels_str} {value}")

            # Histograms
            for name, histograms in self._histograms.items():
                lines.append(f"# TYPE {name} histogram")
                for key, hist in histograms.items():
                    labels_str = self._format_labels(hist.labels)
                    for bucket in hist.buckets:
                        le_str = "+Inf" if bucket.le == float("inf") else str(bucket.le)
                        if hist.labels:
                            bucket_labels = f'{labels_str[:-1]},le="{le_str}"' + "}"
                        else:
                            bucket_labels = f'{{le="{le_str}"}}'
                        lines.append(f"{name}_bucket{bucket_labels} {bucket.count}")
                    lines.append(f"{name}_sum{labels_str} {hist.sum}")
                    lines.append(f"{name}_count{labels_str} {hist.count}")

        return "\n".join(lines)

    def get_sla_summary(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get SLA summary metrics.

        Args:
            tenant_id: Optional tenant to filter by

        Returns:
            Dictionary with SLA metrics
        """
        with self._lock:
            # Calculate error rate
            total_requests = sum(
                v for k, v in self._counters.get(f"{self.prefix}_http_requests_total", {}).items()
                if not tenant_id or f"tenant_id={tenant_id}" in k
            )
            total_errors = sum(
                v for k, v in self._counters.get(f"{self.prefix}_http_errors_total", {}).items()
                if not tenant_id or f"tenant_id={tenant_id}" in k
            )

            error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

            # Get latency percentiles
            latency_name = f"{self.prefix}_http_request_duration_seconds"
            latencies = {}
            for key, hist in self._histograms.get(latency_name, {}).items():
                if tenant_id and f"tenant_id={tenant_id}" not in key:
                    continue
                latencies["p50"] = hist.get_percentile(50)
                latencies["p95"] = hist.get_percentile(95)
                latencies["p99"] = hist.get_percentile(99)

            return {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "error_rate_percent": error_rate,
                "latency_p50_seconds": latencies.get("p50", 0),
                "latency_p95_seconds": latencies.get("p95", 0),
                "latency_p99_seconds": latencies.get("p99", 0),
            }

    def _parse_label_key(self, key: str) -> Dict[str, str]:
        """Parse a label key back into a dictionary."""
        if not key:
            return {}
        labels = {}
        for part in key.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k] = v
        return labels

    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus output."""
        if not labels:
            return ""
        parts = [f'{k}="{v}"' for k, v in labels.items()]
        return "{" + ",".join(parts) + "}"


class Timer:
    """Context manager for timing operations."""

    def __init__(
        self,
        collector: MetricsCollector,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start_time: Optional[float] = None

    def __enter__(self) -> "Timer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration = time.perf_counter() - self.start_time
        self.collector.observe(self.name, duration, self.labels)


# Default collector instance
_default_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the default metrics collector."""
    global _default_collector
    if _default_collector is None:
        _default_collector = MetricsCollector()
    return _default_collector
