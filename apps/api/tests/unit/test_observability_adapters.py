"""Outbound observability adapters — null, stdout, grafana_cloud.

The Grafana Cloud adapter is exercised through `httpx.MockTransport`: the
OTLP payload shape is asserted here, no socket is ever opened.
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import orjson
import pytest

from catetin.adapters.outbound.observability import (
    GrafanaCloudObservability,
    NullObservability,
    SpanHandle,
    StdoutObservability,
)
from catetin.adapters.outbound.observability.otlp import (
    build_otlp_log,
    build_otlp_metric,
    build_otlp_span,
)
from catetin.domain.ports.observability import ObservabilityPort


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [orjson.loads(line) for line in stream.getvalue().splitlines()]


# --- null --------------------------------------------------------------------


async def test_null_adapter_does_nothing_but_still_honours_the_port() -> None:
    adapter: ObservabilityPort = NullObservability()

    assert await adapter.log_event("error", "ignored", user_id=1) is None
    assert await adapter.log_exception(ValueError("ignored")) is None
    assert await adapter.record_metric("ignored_total", 1.0) is None

    span = await adapter.start_span("ignored_op", user_id=1)
    assert isinstance(span, SpanHandle)
    assert await adapter.end_span(span) is None


# --- stdout ------------------------------------------------------------------


async def test_stdout_writes_one_json_line_per_event() -> None:
    stream = io.StringIO()
    adapter = StdoutObservability(stream)

    await adapter.log_event("warning", "parse_failed", user_id=7, reason="no_amount")
    await adapter.record_metric("parse_failure_total", 2.0, {"source": "record"})

    event, metric = _lines(stream)
    assert event == {
        "service": "catetin",
        "type": "event",
        "level": "warning",
        "message": "parse_failed",
        "fields": {"user_id": 7, "reason": "no_amount"},
    }
    assert metric == {
        "service": "catetin",
        "type": "metric",
        "name": "parse_failure_total",
        "value": 2.0,
        "labels": {"source": "record"},
    }


async def test_stdout_logs_exception_with_traceback_and_context() -> None:
    stream = io.StringIO()
    adapter = StdoutObservability(stream)
    try:
        raise ValueError("fpdf2 exploded")
    except ValueError as exc:
        await adapter.log_exception(exc, {"user_id": 7})

    (record,) = _lines(stream)
    assert record["type"] == "exception"
    assert record["level"] == "error"
    assert record["error"] == "ValueError"
    assert record["message"] == "fpdf2 exploded"
    assert record["context"] == {"user_id": 7}
    assert "ValueError: fpdf2 exploded" in record["traceback"]


async def test_stdout_span_reports_duration_and_error() -> None:
    stream = io.StringIO()
    adapter = StdoutObservability(stream)

    span = await adapter.start_span("generate_report", user_id=7)
    await adapter.end_span(span, error=RuntimeError("boom"))

    (record,) = _lines(stream)
    assert record["type"] == "span"
    assert record["operation"] == "generate_report"
    assert record["attributes"] == {"user_id": 7}
    assert record["error"] == "RuntimeError: boom"
    assert record["duration_ms"] >= 0


# --- OTLP payload builders ---------------------------------------------------


def test_otlp_log_shape() -> None:
    payload = build_otlp_log("warning", "parse_failed", {"user_id": 7, "ok": False})

    record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert record["severityNumber"] == 13
    assert record["severityText"] == "WARNING"
    assert record["body"] == {"stringValue": "parse_failed"}
    assert record["attributes"] == [
        # 64-bit ints are strings in protobuf-JSON; bool must not become 0/1.
        {"key": "user_id", "value": {"intValue": "7"}},
        {"key": "ok", "value": {"boolValue": False}},
    ]
    resource = payload["resourceLogs"][0]["resource"]
    assert resource["attributes"] == [
        {"key": "service.name", "value": {"stringValue": "catetin"}}
    ]
    assert record["timeUnixNano"].isdigit()


def test_otlp_log_falls_back_to_info_for_unknown_levels() -> None:
    payload = build_otlp_log("nonsense", "msg", {})
    record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert record["severityNumber"] == 9


def test_otlp_metric_shape() -> None:
    payload = build_otlp_metric("parse_failure_total", 2, {"source": "record"})

    metric = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
    assert metric["name"] == "parse_failure_total"
    point = metric["gauge"]["dataPoints"][0]
    assert point["asDouble"] == 2.0
    assert point["attributes"] == [
        {"key": "source", "value": {"stringValue": "record"}}
    ]


def test_otlp_span_shape_carries_error_status() -> None:
    span = SpanHandle(operation="generate_report", attributes={"user_id": 7})
    payload = build_otlp_span(span, RuntimeError("boom"))

    record = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert record["name"] == "generate_report"
    assert len(record["traceId"]) == 32
    assert len(record["spanId"]) == 16
    assert int(record["endTimeUnixNano"]) >= int(record["startTimeUnixNano"])
    assert record["status"] == {"code": 2, "message": "RuntimeError: boom"}


def test_otlp_span_without_error_has_no_status() -> None:
    payload = build_otlp_span(SpanHandle(operation="ok_op"))
    assert "status" not in payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


# --- grafana_cloud -----------------------------------------------------------


@pytest.fixture
def captured() -> list[httpx.Request]:
    return []


@pytest.fixture
def client(captured: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_grafana_cloud_posts_logs_to_the_otlp_logs_path(
    client: httpx.AsyncClient, captured: list[httpx.Request]
) -> None:
    adapter = GrafanaCloudObservability(client, "http://alloy:4318")

    await adapter.log_event("warning", "parse_failed", user_id=7)

    (request,) = captured
    assert request.method == "POST"
    assert str(request.url) == "http://alloy:4318/v1/logs"
    body = orjson.loads(request.content)
    record = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert record["body"] == {"stringValue": "parse_failed"}
    assert record["severityText"] == "WARNING"


async def test_grafana_cloud_posts_metrics_and_traces_to_their_own_paths(
    client: httpx.AsyncClient, captured: list[httpx.Request]
) -> None:
    adapter = GrafanaCloudObservability(client, "http://alloy:4318")

    await adapter.record_metric("parse_failure_total", 1.0, {"source": "record"})
    span = await adapter.start_span("generate_report", user_id=7)
    assert captured[-1].url.path == "/v1/metrics"  # start_span itself sends nothing
    await adapter.end_span(span)

    assert [str(request.url) for request in captured] == [
        "http://alloy:4318/v1/metrics",
        "http://alloy:4318/v1/traces",
    ]


async def test_grafana_cloud_log_exception_carries_type_and_context(
    client: httpx.AsyncClient, captured: list[httpx.Request]
) -> None:
    adapter = GrafanaCloudObservability(client, "http://alloy:4318")

    await adapter.log_exception(ValueError("fpdf2 exploded"), {"user_id": 7})

    body = orjson.loads(captured[0].content)
    record = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert record["severityText"] == "ERROR"
    assert record["body"] == {"stringValue": "fpdf2 exploded"}
    assert {"key": "exception.type", "value": {"stringValue": "ValueError"}} in record[
        "attributes"
    ]
    assert {"key": "user_id", "value": {"intValue": "7"}} in record["attributes"]


async def test_grafana_cloud_strips_a_trailing_slash_from_the_endpoint(
    client: httpx.AsyncClient, captured: list[httpx.Request]
) -> None:
    adapter = GrafanaCloudObservability(client, "http://alloy:4318/")

    await adapter.log_event("info", "hello")

    assert str(captured[0].url) == "http://alloy:4318/v1/logs"


async def test_grafana_cloud_never_raises_when_the_collector_is_down(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A dead collector must cost telemetry, not the business operation."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GrafanaCloudObservability(client, "http://alloy:4318")

    await adapter.log_event("error", "still fine")
    await adapter.record_metric("still_fine_total", 1.0)
    await adapter.end_span(await adapter.start_span("still_fine"))

    assert "observability: dropped /v1/logs" in capsys.readouterr().err
