"""Minimal OTLP/HTTP JSON payload builders.

`opentelemetry-proto` (and the whole OTel SDK) is deliberately NOT a
dependency — the host budget is 400 MB RSS and we emit a handful of events,
not a trace firehose. OTLP/HTTP accepts a JSON encoding of the same protobuf
messages, which is a few dozen lines to build by hand:

    logs    -> POST {endpoint}/v1/logs     {"resourceLogs":    [...]}
    metrics -> POST {endpoint}/v1/metrics  {"resourceMetrics": [...]}
    traces  -> POST {endpoint}/v1/traces   {"resourceSpans":   [...]}

Note the protobuf-JSON quirks this encoding has to honour: 64-bit fields
(`timeUnixNano`, `asInt`) are STRINGS, and every attribute value is wrapped
in a one-of ("AnyValue") object rather than being a bare JSON scalar.
"""

from __future__ import annotations

import time
from typing import Any

from .span import SpanHandle

SCOPE_NAME = "catetin"

# OTLP SeverityNumber (logs data model). Anything unrecognised falls back to
# INFO rather than being dropped.
_SEVERITY_NUMBERS = {
    "trace": 1,
    "debug": 5,
    "info": 9,
    "warning": 13,
    "warn": 13,
    "error": 17,
    "critical": 21,
    "fatal": 21,
}
_DEFAULT_SEVERITY = 9

# Status.StatusCode.STATUS_CODE_ERROR
_STATUS_ERROR = 2


def _any_value(value: Any) -> dict[str, Any]:
    """Wrap a Python value as an OTLP AnyValue."""
    # bool before int — bool is a subclass of int and would otherwise be
    # emitted as 0/1.
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    return {"stringValue": str(value)}


def _attributes(fields: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": key, "value": _any_value(value)} for key, value in fields.items()]


def _resource(service_name: str) -> dict[str, Any]:
    return {"attributes": _attributes({"service.name": service_name})}


def build_otlp_log(
    level: str,
    message: str,
    fields: dict[str, Any],
    *,
    service_name: str = SCOPE_NAME,
    timestamp_unix_nano: int | None = None,
) -> dict[str, Any]:
    """One log record, ready to POST to `{endpoint}/v1/logs`."""
    now = time.time_ns() if timestamp_unix_nano is None else timestamp_unix_nano
    return {
        "resourceLogs": [
            {
                "resource": _resource(service_name),
                "scopeLogs": [
                    {
                        "scope": {"name": SCOPE_NAME},
                        "logRecords": [
                            {
                                "timeUnixNano": str(now),
                                "observedTimeUnixNano": str(now),
                                "severityNumber": _SEVERITY_NUMBERS.get(
                                    level.lower(), _DEFAULT_SEVERITY
                                ),
                                "severityText": level.upper(),
                                "body": {"stringValue": message},
                                "attributes": _attributes(fields),
                            }
                        ],
                    }
                ],
            }
        ]
    }


def build_otlp_metric(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
    *,
    service_name: str = SCOPE_NAME,
    timestamp_unix_nano: int | None = None,
) -> dict[str, Any]:
    """One gauge sample, ready to POST to `{endpoint}/v1/metrics`.

    Gauge rather than sum: `record_metric` takes an arbitrary value with no
    notion of a start time or monotonicity, which is exactly the gauge
    contract. Counters are derived downstream in Mimir/PromQL.
    """
    now = time.time_ns() if timestamp_unix_nano is None else timestamp_unix_nano
    return {
        "resourceMetrics": [
            {
                "resource": _resource(service_name),
                "scopeMetrics": [
                    {
                        "scope": {"name": SCOPE_NAME},
                        "metrics": [
                            {
                                "name": name,
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": str(now),
                                            "asDouble": float(value),
                                            "attributes": _attributes(dict(labels or {})),
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


def build_otlp_span(
    span: SpanHandle,
    error: BaseException | None = None,
    *,
    service_name: str = SCOPE_NAME,
    end_unix_nano: int | None = None,
) -> dict[str, Any]:
    """One finished span, ready to POST to `{endpoint}/v1/traces`."""
    end = time.time_ns() if end_unix_nano is None else end_unix_nano
    record: dict[str, Any] = {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "name": span.operation,
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(span.start_unix_nano),
        "endTimeUnixNano": str(end),
        "attributes": _attributes(span.attributes),
    }
    if error is not None:
        record["status"] = {
            "code": _STATUS_ERROR,
            "message": f"{type(error).__name__}: {error}",
        }
    return {
        "resourceSpans": [
            {
                "resource": _resource(service_name),
                "scopeSpans": [{"scope": {"name": SCOPE_NAME}, "spans": [record]}],
            }
        ]
    }
