"""FakeObservability — ObservabilityPort double that records what was emitted."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoggedEvent:
    level: str
    message: str
    fields: dict[str, Any]


@dataclass
class LoggedException:
    error: BaseException
    context: dict[str, Any]


@dataclass
class RecordedMetric:
    name: str
    value: float
    labels: dict[str, str]


@dataclass
class RecordedSpan:
    operation: str
    attributes: dict[str, Any]
    ended: bool = False
    error: BaseException | None = None


@dataclass
class FakeObservability:
    events: list[LoggedEvent] = field(default_factory=list)
    exceptions: list[LoggedException] = field(default_factory=list)
    metrics: list[RecordedMetric] = field(default_factory=list)
    spans: list[RecordedSpan] = field(default_factory=list)

    async def log_event(self, level: str, message: str, **fields: Any) -> None:
        self.events.append(LoggedEvent(level=level, message=message, fields=fields))

    async def log_exception(
        self, error: BaseException, context: dict[str, Any] | None = None
    ) -> None:
        self.exceptions.append(LoggedException(error=error, context=context or {}))

    async def record_metric(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        self.metrics.append(RecordedMetric(name=name, value=value, labels=labels or {}))

    async def start_span(self, operation: str, **attributes: Any) -> Any:
        span = RecordedSpan(operation=operation, attributes=dict(attributes))
        self.spans.append(span)
        return span

    async def end_span(self, span: Any, error: BaseException | None = None) -> None:
        span.ended = True
        span.error = error

    def messages(self) -> list[str]:
        return [event.message for event in self.events]
