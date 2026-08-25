"""Outbound observability adapters — pick one in `composition.wire()`.

`null` (default, test-safe) · `stdout` (local dev) · `grafana_cloud` (OTLP
to the Alloy collector). All three satisfy `ObservabilityPort`; the
application layer imports none of them.
"""

from .grafana_cloud import GrafanaCloudObservability
from .null import NullObservability
from .span import SpanHandle
from .stdout import StdoutObservability

__all__ = [
    "GrafanaCloudObservability",
    "NullObservability",
    "SpanHandle",
    "StdoutObservability",
]
