"""GrafanaCloudObservability -> ObservabilityPort, via OTLP/HTTP.

Ships application-level telemetry to the local Alloy collector (default
`http://alloy:4318`), which forwards it to Grafana Cloud — Loki for logs,
Mimir for metrics, Tempo for traces. The app never holds Grafana Cloud
credentials: those live in Alloy's config, one hop away.

Every send is best-effort. Telemetry that fails must not fail the business
operation that emitted it, so `_post` swallows *all* exceptions and reports
them on stderr instead of raising. It reuses the app's single shared
`httpx.AsyncClient` (per the FRD's one-client rule).
"""

from __future__ import annotations

import sys
from typing import Any

import httpx

from .otlp import build_otlp_log, build_otlp_metric, build_otlp_span
from .span import SpanHandle


class GrafanaCloudObservability:
    def __init__(
        self,
        client: httpx.AsyncClient,
        otlp_endpoint: str,
        *,
        service_name: str = "catetin",
        timeout: float = 2.0,
    ) -> None:
        self._client = client
        # Trailing slashes would produce `//v1/logs`, which some collectors 404.
        self._endpoint = otlp_endpoint.rstrip("/")
        self._service = service_name
        self._timeout = timeout

    async def _post(self, signal_path: str, payload: dict[str, Any]) -> None:
        try:
            await self._client.post(
                f"{self._endpoint}{signal_path}", json=payload, timeout=self._timeout
            )
        except Exception as exc:  # noqa: BLE001 - telemetry must never break the caller
            print(
                f"observability: dropped {signal_path} ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )

    async def log_event(self, level: str, message: str, **fields: Any) -> None:
        await self._post(
            "/v1/logs", build_otlp_log(level, message, fields, service_name=self._service)
        )

    async def log_exception(
        self, error: BaseException, context: dict[str, Any] | None = None
    ) -> None:
        fields: dict[str, Any] = {"exception.type": type(error).__name__}
        fields.update(context or {})
        await self._post(
            "/v1/logs",
            build_otlp_log("error", str(error) or type(error).__name__, fields,
                           service_name=self._service),
        )

    async def record_metric(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        await self._post(
            "/v1/metrics", build_otlp_metric(name, value, labels, service_name=self._service)
        )

    async def start_span(self, operation: str, **attributes: Any) -> Any:
        # Nothing is sent until the span ends — OTLP has no "span started"
        # message; a span is exported once, complete, with its duration.
        return SpanHandle(operation=operation, attributes=dict(attributes))

    async def end_span(self, span: Any, error: BaseException | None = None) -> None:
        if not isinstance(span, SpanHandle):
            return
        await self._post(
            "/v1/traces", build_otlp_span(span, error, service_name=self._service)
        )
