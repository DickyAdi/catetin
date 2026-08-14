"""LLMParser — Phase 2 fallback for low-confidence regex parses.

Present so the interface exists in Phase 1/2, but unwired: composition.py
never constructs this, and LLM_ENABLED stays false. The 9router gateway
call lands with LlmGatewayPort in a later phase.
"""

from __future__ import annotations

from datetime import date

from ....domain.models import ParsedTransaction


class LLMParser:
    """Implements ParserPort; not usable until Phase 2 wires the gateway."""

    async def parse(
        self, text: str, *, today: date, slang_enabled: bool = True
    ) -> list[ParsedTransaction]:
        raise NotImplementedError("LLMParser is not implemented yet (Phase 2)")
