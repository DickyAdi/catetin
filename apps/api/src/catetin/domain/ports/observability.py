"""ObservabilityPort — the application layer's only view of telemetry.

Use cases emit events/metrics/spans through this Protocol; which backend
receives them (Grafana Cloud via OTLP, stdout, or nothing at all) is decided
once, in `composition.wire()`. Swapping backends therefore never touches the
application layer — see the Observability design doc, section 6.

Every method is async and MUST be treated as best-effort by adapters: a
telemetry failure is never allowed to fail the business operation that
emitted it.
"""

from typing import Any, Protocol


class ObservabilityPort(Protocol):
    async def log_event(self, level: str, message: str, **fields: Any) -> None:
        """Emit a structured log event (`info`/`warning`/`error` + fields)."""
        ...

    async def log_exception(
        self, error: BaseException, context: dict[str, Any] | None = None
    ) -> None:
        """Emit an exception with its traceback and optional context."""
        ...

    async def record_metric(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Emit a metric sample, e.g. `parse_failure_total`."""
        ...

    async def start_span(self, operation: str, **attributes: Any) -> Any:
        """Begin a trace span; returns an opaque, adapter-specific handle."""
        ...

    async def end_span(self, span: Any, error: BaseException | None = None) -> None:
        """Finish a span previously returned by `start_span`."""
        ...
