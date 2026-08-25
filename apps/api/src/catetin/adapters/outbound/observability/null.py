"""NullObservability -> ObservabilityPort. Telemetry off.

The default everywhere `observability_backend` is unset: tests, local runs,
and any deployment that has not been pointed at a collector yet. Every
method is a no-op so nothing ever waits on the network.
"""

from __future__ import annotations

from typing import Any

from .span import SpanHandle


class NullObservability:
    async def log_event(self, level: str, message: str, **fields: Any) -> None:
        return None

    async def log_exception(
        self, error: BaseException, context: dict[str, Any] | None = None
    ) -> None:
        return None

    async def record_metric(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        return None

    async def start_span(self, operation: str, **attributes: Any) -> Any:
        # Still returns a real handle: callers pass it back to `end_span`, and
        # handing out None would make the null adapter the odd one out.
        return SpanHandle(operation=operation, attributes=dict(attributes))

    async def end_span(self, span: Any, error: BaseException | None = None) -> None:
        return None
