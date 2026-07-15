from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ObservabilityManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._tracer = None
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        if not self.settings.prometheus_enabled:
            return

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource

            resource = Resource.create({
                "service.name": "dental-ai-chatbot",
                "service.version": "1.0.0",
            })
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint="localhost:4317", insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer("dental-ai-chatbot")
            self._initialized = True
            logger.info("OpenTelemetry initialized")
        except Exception as exc:
            logger.warning(f"OpenTelemetry initialization failed: {exc}")
            self._tracer = None

    def trace_operation(self, name: str, attributes: dict[str, Any] | None = None):
        if not self._tracer:
            return _DummySpan()
        from opentelemetry import trace
        span = self._tracer.start_span(name, attributes=attributes or {})
        return span

    def record_metric(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        try:
            from prometheus_client import Histogram, Counter, Gauge

            if not hasattr(self, "_metrics"):
                self._metrics = {}

            if name not in self._metrics:
                if "duration" in name or "latency" in name:
                    self._metrics[name] = Histogram(name, f"{name} metric", list(tags.keys()) if tags else [], buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0])
                elif "count" in name or "total" in name:
                    self._metrics[name] = Counter(name, f"{name} metric", list(tags.keys()) if tags else [])
                else:
                    self._metrics[name] = Gauge(name, f"{name} metric", list(tags.keys()) if tags else [])

            metric = self._metrics[name]
            if isinstance(metric, Histogram):
                metric.labels(**(tags or {})).observe(value)
            elif isinstance(metric, Counter):
                metric.labels(**(tags or {})).inc(value)
            elif isinstance(metric, Gauge):
                metric.labels(**(tags or {})).set(value)
        except Exception:
            pass


class _DummySpan:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def set_attribute(self, key: str, value: Any) -> None:
        pass
    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass


observability = ObservabilityManager()
