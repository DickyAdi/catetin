from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_occurred_on(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("occurred_on must be a YYYY-MM-DD date string") from exc
    return value


class User(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    platform: Literal["telegram", "whatsapp"]
    platform_user_id: str
    display_name: str | None = None
    business_name: str | None = None
    timezone: str = "Asia/Jakarta"
    digest_enabled: bool = True
    blocked_at: int | None = None
    created_at: int
    updated_at: int


class Transaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    user_id: int
    kind: Literal["sale", "expense"]
    item: str
    qty: int = Field(default=1, gt=0)
    unit_amount: int | None = Field(default=None, ge=0)
    total_amount: int = Field(gt=0)
    occurred_on: str  # YYYY-MM-DD, user-local
    occurred_at: int  # unix epoch, ordering
    source: Literal["regex", "llm", "manual"] = "regex"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_text: str | None = Field(default=None, max_length=500)
    created_at: int
    deleted_at: int | None = None

    @field_validator("occurred_on")
    @classmethod
    def _check_occurred_on(cls, value: str) -> str:
        return _validate_occurred_on(value)


class ParsedTransaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sale", "expense"] | None  # None = ambiguous, ask user
    item: str = Field(max_length=80)
    qty: int = Field(default=1, gt=0)
    unit_amount: int | None = Field(default=None, ge=0)
    total_amount: int = Field(gt=0)
    occurred_on: date  # user-local
    confidence: float = Field(ge=0.0, le=1.0)
    raw_text: str = Field(max_length=500)

    @field_validator("item")
    @classmethod
    def _check_item_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("item must not be blank")
        return stripped


class Summary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    income: int = Field(ge=0)
    expense: int = Field(ge=0)
    profit: int
    count: int = Field(ge=0)


class DayTotal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    date: str  # YYYY-MM-DD
    income: int = Field(ge=0)
    expense: int = Field(ge=0)
    profit: int

    @field_validator("date")
    @classmethod
    def _check_date(cls, value: str) -> str:
        return _validate_occurred_on(value)


class ItemTotal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item: str
    kind: Literal["sale", "expense"]
    total: int = Field(ge=0)


class ParseFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int | None = None
    user_id: int | None = None
    raw_text: str
    reason: str
    created_at: int


class FailedSegment(BaseModel):
    """One segment the parser could not turn into a transaction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_text: str = Field(max_length=500)
    reason: str  # no_amount | too_many_segments | amount_too_large | no_item


class ParseOutcome(BaseModel):
    """Richer result than `ParserPort.parse` — carries failure reasons too."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parsed: list[ParsedTransaction]
    failures: list[FailedSegment]
