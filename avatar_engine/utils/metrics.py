"""
Metrics collection and export for Avatar Engine.

Provides optional Prometheus/OpenTelemetry integration.
Falls back to simple in-memory metrics if external libs not installed.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Try to import prometheus_client
_PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    pass


@dataclass
class MetricsConfig:
    """
    Metrics configuration.

    Attributes:
        enabled: Whether metrics collection is active
        type: Metrics backend type ("prometheus", "opentelemetry", "simple")
        port: HTTP port for metrics endpoint (Prometheus)
        endpoint: HTTP endpoint path (Prometheus)
    """
    enabled: bool = False
    type: str = "simple"  # prometheus, opentelemetry, simple
    port: int = 9090
    endpoint: str = "/metrics"


class SimpleMetrics:
    """
    Simple in-memory metrics collector (no external dependencies).

    Provides basic counters and histograms for monitoring.
    """

    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}
        self._histograms: Dict[str, list] = {}
        self._gauges: Dict[str, float] = {}
        self._start_time = time.time()

    def inc_counter(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter."""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram observation."""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge value."""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> int:
        """Get counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_histogram_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "sum": 0, "min": 0, "max": 0, "avg": 0}
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0.0)

    def get_all(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary."""
        return {
            "counters": dict(self._counters),
            "histograms": {k: self.get_histogram_stats(k) for k in self._histograms},
            "gauges": dict(self._gauges),
            "uptime_seconds": time.time() - self._start_time,
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._histograms.clear()
        self._gauges.clear()
        self._start_time = time.time()

    @staticmethod
    def _make_key(name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


class PrometheusMetrics:
    """
    Prometheus metrics collector.

    Requires prometheus_client package:
        pip install prometheus-client
    """

    def __init__(self, port: int = 9090) -> None:
        if not _PROMETHEUS_AVAILABLE:
            raise ImportError(
                "prometheus_client not installed. "
                "Install with: pip install prometheus-client"
            )

        self._port = port
        self._server_started = False

        # Define metrics
        self._requests_total = Counter(
            "avatar_requests_total",
            "Total requests",
            ["provider", "status"],
        )
        self._request_duration = Histogram(
            "avatar_request_duration_seconds",
            "Request duration in seconds",
            ["provider"],
        )
        self._active_sessions = Gauge(
            "avatar_active_sessions",
            "Active sessions",
            ["provider"],
        )
        self._cost_total = Counter(
            "avatar_cost_usd_total",
            "Total cost in USD",
            ["provider"],
        )
        self._tokens_total = Counter(
            "avatar_tokens_total",
            "Total tokens used",
            ["provider", "type"],
        )

    def start_server(self) -> None:
        """Start the Prometheus HTTP server."""
        if not self._server_started:
            start_http_server(self._port)
            self._server_started = True

    def record_request(self, provider: str, success: bool, duration_ms: int) -> None:
        """Record a request."""
        status = "success" if success else "error"
        self._requests_total.labels(provider=provider, status=status).inc()
        self._request_duration.labels(provider=provider).observe(duration_ms / 1000)

    def record_cost(self, provider: str, cost_usd: float) -> None:
        """Record cost."""
        self._cost_total.labels(provider=provider).inc(cost_usd)

    def record_tokens(self, provider: str, input_tokens: int, output_tokens: int) -> None:
        """Record token usage."""
        self._tokens_total.labels(provider=provider, type="input").inc(input_tokens)
        self._tokens_total.labels(provider=provider, type="output").inc(output_tokens)

    def set_active_sessions(self, provider: str, count: int) -> None:
        """Set active session count."""
        self._active_sessions.labels(provider=provider).set(count)


class EngineMetrics:
    """
    Avatar Engine metrics collector.

    Automatically chooses backend based on configuration and available libraries.
    """

    def __init__(self, config: Optional[MetricsConfig] = None) -> None:
        self._config = config or MetricsConfig()
        self._backend: Any = None

        if self._config.enabled:
            if self._config.type == "prometheus" and _PROMETHEUS_AVAILABLE:
                self._backend = PrometheusMetrics(port=self._config.port)
            else:
                self._backend = SimpleMetrics()
        else:
            self._backend = SimpleMetrics()

    @property
    def is_enabled(self) -> bool:
        """Check if metrics are enabled."""
        return self._config.enabled

    @property
    def backend_type(self) -> str:
        """Get current backend type."""
        if isinstance(self._backend, PrometheusMetrics):
            return "prometheus"
        return "simple"

    def start_server(self) -> None:
        """Start metrics HTTP server (Prometheus only)."""
        if isinstance(self._backend, PrometheusMetrics):
            self._backend.start_server()

    def record_request(
        self,
        provider: str,
        success: bool,
        duration_ms: int,
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record a completed request."""
        if isinstance(self._backend, PrometheusMetrics):
            self._backend.record_request(provider, success, duration_ms)
            if cost_usd > 0:
                self._backend.record_cost(provider, cost_usd)
            if input_tokens > 0 or output_tokens > 0:
                self._backend.record_tokens(provider, input_tokens, output_tokens)
        else:
            # Simple metrics
            status = "success" if success else "error"
            self._backend.inc_counter("requests_total", labels={"provider": provider, "status": status})
            self._backend.observe_histogram("request_duration_ms", duration_ms, labels={"provider": provider})
            if cost_usd > 0:
                self._backend.inc_counter("cost_usd", int(cost_usd * 100), labels={"provider": provider})
            if input_tokens > 0:
                self._backend.inc_counter("tokens", input_tokens, labels={"provider": provider, "type": "input"})
            if output_tokens > 0:
                self._backend.inc_counter("tokens", output_tokens, labels={"provider": provider, "type": "output"})

    def set_active_sessions(self, provider: str, count: int) -> None:
        """Set active session count."""
        if isinstance(self._backend, PrometheusMetrics):
            self._backend.set_active_sessions(provider, count)
        else:
            self._backend.set_gauge("active_sessions", count, labels={"provider": provider})

    def get_all(self) -> Dict[str, Any]:
        """Get all metrics (simple backend only)."""
        if isinstance(self._backend, SimpleMetrics):
            return self._backend.get_all()
        return {"note": "Use Prometheus endpoint for metrics"}


def is_prometheus_available() -> bool:
    """Check if prometheus_client is installed."""
    return _PROMETHEUS_AVAILABLE
