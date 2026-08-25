"""The span handle every observability adapter hands back from `start_span`.

`ObservabilityPort.start_span` is typed as returning `Any` on purpose — the
handle is adapter-specific and the application layer only ever passes it
straight back to `end_span`. All three shipped adapters happen to agree on
this shape, so it lives here rather than being duplicated per adapter.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SpanHandle:
    operation: str
    attributes: dict[str, Any] = field(default_factory=dict)
    start_unix_nano: int = field(default_factory=time.time_ns)
    # 16-byte trace id / 8-byte span id, hex-encoded — the OTLP/JSON encoding.
    trace_id: str = field(default_factory=lambda: secrets.token_hex(16))
    span_id: str = field(default_factory=lambda: secrets.token_hex(8))
