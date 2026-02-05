"""Tests for avatar_engine.utils.metrics module."""

import pytest
from avatar_engine.utils.metrics import (
    SimpleMetrics,
    MetricsConfig,
    EngineMetrics,
    is_prometheus_available,
)


class TestMetricsConfig:
    """Tests for MetricsConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        cfg = MetricsConfig()
        assert cfg.enabled is False
        assert cfg.type == "simple"
        assert cfg.port == 9090
        assert cfg.endpoint == "/metrics"

    def test_custom_values(self):
        """Should accept custom values."""
        cfg = MetricsConfig(enabled=True, type="prometheus", port=8080)
        assert cfg.enabled is True
        assert cfg.type == "prometheus"
        assert cfg.port == 8080


class TestSimpleMetrics:
    """Tests for SimpleMetrics class."""

    def test_counter(self):
        """Should track counters correctly."""
        metrics = SimpleMetrics()
        metrics.inc_counter("requests")
        metrics.inc_counter("requests")
        metrics.inc_counter("requests", 3)
        assert metrics.get_counter("requests") == 5

    def test_counter_with_labels(self):
        """Should track counters with labels separately."""
        metrics = SimpleMetrics()
        metrics.inc_counter("requests", labels={"provider": "gemini"})
        metrics.inc_counter("requests", labels={"provider": "claude"})
        metrics.inc_counter("requests", labels={"provider": "gemini"})

        assert metrics.get_counter("requests", labels={"provider": "gemini"}) == 2
        assert metrics.get_counter("requests", labels={"provider": "claude"}) == 1

    def test_histogram(self):
        """Should track histogram observations."""
        metrics = SimpleMetrics()
        metrics.observe_histogram("duration", 100)
        metrics.observe_histogram("duration", 200)
        metrics.observe_histogram("duration", 150)

        stats = metrics.get_histogram_stats("duration")
        assert stats["count"] == 3
        assert stats["sum"] == 450
        assert stats["min"] == 100
        assert stats["max"] == 200
        assert stats["avg"] == 150

    def test_histogram_empty(self):
        """Should handle empty histogram."""
        metrics = SimpleMetrics()
        stats = metrics.get_histogram_stats("nonexistent")
        assert stats["count"] == 0

    def test_gauge(self):
        """Should track gauges correctly."""
        metrics = SimpleMetrics()
        metrics.set_gauge("active_sessions", 5)
        assert metrics.get_gauge("active_sessions") == 5
        metrics.set_gauge("active_sessions", 3)
        assert metrics.get_gauge("active_sessions") == 3

    def test_get_all(self):
        """Should return all metrics."""
        metrics = SimpleMetrics()
        metrics.inc_counter("requests")
        metrics.observe_histogram("duration", 100)
        metrics.set_gauge("sessions", 2)

        all_metrics = metrics.get_all()
        assert "counters" in all_metrics
        assert "histograms" in all_metrics
        assert "gauges" in all_metrics
        assert "uptime_seconds" in all_metrics

    def test_reset(self):
        """Should reset all metrics."""
        metrics = SimpleMetrics()
        metrics.inc_counter("requests")
        metrics.observe_histogram("duration", 100)
        metrics.set_gauge("sessions", 2)

        metrics.reset()

        assert metrics.get_counter("requests") == 0
        assert metrics.get_histogram_stats("duration")["count"] == 0
        assert metrics.get_gauge("sessions") == 0.0


class TestEngineMetrics:
    """Tests for EngineMetrics class."""

    def test_default_uses_simple(self):
        """Default should use simple metrics backend."""
        metrics = EngineMetrics()
        assert metrics.backend_type == "simple"

    def test_disabled_by_default(self):
        """Metrics should be disabled by default."""
        cfg = MetricsConfig()
        metrics = EngineMetrics(cfg)
        # Still creates simple backend for stats
        assert metrics.backend_type == "simple"

    def test_enabled_simple(self):
        """Should use simple backend when enabled."""
        cfg = MetricsConfig(enabled=True, type="simple")
        metrics = EngineMetrics(cfg)
        assert metrics.is_enabled is True
        assert metrics.backend_type == "simple"

    def test_record_request(self):
        """Should record request metrics."""
        metrics = EngineMetrics()
        metrics.record_request(
            provider="gemini",
            success=True,
            duration_ms=1500,
            cost_usd=0.01,
            input_tokens=100,
            output_tokens=200,
        )

        all_metrics = metrics.get_all()
        assert "counters" in all_metrics

    def test_set_active_sessions(self):
        """Should set active session gauge."""
        metrics = EngineMetrics()
        metrics.set_active_sessions("gemini", 3)
        all_metrics = metrics.get_all()
        assert "gauges" in all_metrics


class TestPrometheusAvailability:
    """Tests for Prometheus availability check."""

    def test_is_prometheus_available(self):
        """Should return boolean."""
        result = is_prometheus_available()
        assert isinstance(result, bool)


class TestMetricsConfigIntegration:
    """Integration tests for metrics configuration."""

    def test_config_to_dict_includes_metrics(self):
        """Config.to_dict should include metrics settings."""
        from avatar_engine.config import AvatarConfig

        config = AvatarConfig(
            metrics_enabled=True,
            metrics_type="prometheus",
            metrics_port=8080,
        )
        d = config.to_dict()

        assert d["metrics"]["enabled"] is True
        assert d["metrics"]["type"] == "prometheus"
        assert d["metrics"]["port"] == 8080

    def test_config_from_dict_loads_metrics(self):
        """Config.from_dict should load metrics settings."""
        from avatar_engine.config import AvatarConfig

        config = AvatarConfig.from_dict({
            "metrics": {
                "enabled": True,
                "type": "opentelemetry",
                "port": 9999,
            }
        })

        assert config.metrics_enabled is True
        assert config.metrics_type == "opentelemetry"
        assert config.metrics_port == 9999
