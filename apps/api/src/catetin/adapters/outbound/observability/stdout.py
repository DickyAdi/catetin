"""StdoutObservability -> ObservabilityPort. One JSON line per event.

The local-dev backend: no collector, no network, no credentials. It is also
the shape Alloy's `loki.source.docker` expects when the API runs in Docker —
stdout is already being tailed, so structured lines land in Loki for free.
"""

from __future__ import annotations

import sys
import time
import traceback
from typing import Any, TextIO

import orjson

from .span import SpanHandle


class StdoutObservability:
    def __init__(self, stream: TextIO | None = None, service_name: str = "catetin") -> None:
        # `stream` is injectable so tests can capture without touching sys.stdout.
        self._stream = stream if stream is not None else sys.stdout
        self._service = service_name

    def _emit(self, record: dict[str, Any]) -> None:
        line = orjson.dumps({"service": self._service, **record}).decode()
        self._stream.write(line + "\n")
        self._stream.flush()

    async def log_event(self, level: str, message: str, **fields: Any) -> None:
        self._emit(
            {
                "type": "event",
                "level": level,
                "message": message,
                "fields": fields,
            }
        )

    async def log_exception(
        self, error: BaseException, context: dict[str, Any] | None = None
    ) -> None:
        self._emit(
            {
                "type": "exception",
                "level": "error",
                "error": type(error).__name__,
                "message": str(error),
                "traceback": "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                ),
                "context": context or {},
            }
        )

    async def record_metric(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        self._emit(
            {
                "type": "metric",
                "name": name,
                "value": float(value),
                "labels": labels or {},
            }
        )

    async def start_span(self, operation: str, **attributes: Any) -> Any:
        return SpanHandle(operation=operation, attributes=dict(attributes))

    async def end_span(self, span: Any, error: BaseException | None = None) -> None:
        if not isinstance(span, SpanHandle):
            return
        self._emit(
            {
                "type": "span",
                "operation": span.operation,
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "duration_ms": (time.time_ns() - span.start_unix_nano) / 1_000_000,
                "attributes": span.attributes,
                "error": None if error is None else f"{type(error).__name__}: {error}",
            }
        )
