from typing import Protocol

from ..models import ParsedTransaction

# Phase 2 placeholder. No adapter implements this in Phase 1; LLM_ENABLED
# stays false and nothing in the composition root wires this port yet.


class LlmGatewayPort(Protocol):
    """Outbound call to the 9router LLM gateway for fallback parsing."""

    async def parse(self, text: str) -> list[ParsedTransaction]: ...
