"""The application layer talks to ObservabilityPort, nothing else.

These tests assert the *contract* — which events/metrics a use case emits and
with what arguments — against a fake adapter. Whether the payload ends up in
Loki or on stdout is the adapter's business, covered in
`test_observability_adapters.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from catetin.application.generate_report import GenerateReport
from catetin.application.onboarding import Onboarding
from catetin.application.record_transactions import RecordTransactions
from catetin.domain.models import FailedSegment, ParsedTransaction, ParseOutcome
from catetin.domain.ports.observability import ObservabilityPort
from tests.fakes.fake_observability import FakeObservability
from tests.fakes.fake_parser import FakeParser
from tests.fakes.fake_repositories import (
    FakeRateLimiter,
    FakeReportRenderer,
    FakeUnitOfWork,
)
from tests.fakes.frozen_clock import FrozenClock

TODAY = date(2026, 8, 15)


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork(FrozenClock(datetime(2026, 8, 15, 12, 0, tzinfo=UTC)))


@pytest.fixture
def obs() -> FakeObservability:
    return FakeObservability()


def _parsed(kind: str | None, item: str, total_amount: int = 10_000) -> ParsedTransaction:
    return ParsedTransaction(
        kind=kind,  # type: ignore[arg-type]
        item=item,
        qty=1,
        unit_amount=None,
        total_amount=total_amount,
        occurred_on=TODAY,
        confidence=1.0,
        raw_text=f"{item} {total_amount}",
        flagged=False,
    )


async def _create_user(uow: FakeUnitOfWork) -> int:
    user = await Onboarding(uow).get_or_create_user("telegram", "9001", "Budi")
    return user.id


def test_fake_satisfies_the_port() -> None:
    """Structural check: the double really implements ObservabilityPort, so a
    green suite means the use cases were exercised against the real shape."""
    adapter: ObservabilityPort = FakeObservability()
    assert adapter is not None


# --- RecordTransactions ------------------------------------------------------


async def test_parse_failures_are_logged_with_reason_and_segment_length(
    uow: FakeUnitOfWork, obs: FakeObservability
) -> None:
    """The failure reason and how long the segment was, never the segment.

    Telemetry leaves for Grafana Cloud, and `/hapusakun` cannot reach a
    third-party system — so verbatim chat text must not be in the payload."""
    user_id = await _create_user(uow)
    parser = FakeParser()
    parser.next_outcome = ParseOutcome(
        parsed=[_parsed("sale", "Kopi", 15_000)],
        failures=[FailedSegment(raw_text="laris manis hari ini", reason="no_amount")],
    )

    await RecordTransactions(parser, uow, observability=obs).execute(user_id, "raw", TODAY)

    assert len(obs.events) == 1
    event = obs.events[0]
    assert event.level == "warning"
    assert event.message == "parse_failed"
    assert event.fields == {
        "user_id": user_id,
        "reason": "no_amount",
        "segment_len": 20,
    }
    assert "laris manis hari ini" not in repr(event.fields)


async def test_ambiguous_kind_is_logged_and_counted(
    uow: FakeUnitOfWork, obs: FakeObservability
) -> None:
    user_id = await _create_user(uow)
    parser = FakeParser()
    parser.next_outcome = ParseOutcome(
        parsed=[_parsed(None, "Nasi Goreng", 25_000), _parsed(None, "Es Teh", 5_000)],
        failures=[],
    )

    await RecordTransactions(parser, uow, observability=obs).execute(user_id, "raw", TODAY)

    assert [event.fields["reason"] for event in obs.events] == [
        "ambiguous_kind",
        "ambiguous_kind",
    ]
    assert len(obs.metrics) == 1
    metric = obs.metrics[0]
    assert metric.name == "parse_failure_total"
    assert metric.value == 2.0
    assert metric.labels == {"source": "record_transactions"}


async def test_clean_batch_emits_no_telemetry(
    uow: FakeUnitOfWork, obs: FakeObservability
) -> None:
    """No issues, no noise — the free tier is 50 GB, not infinite."""
    user_id = await _create_user(uow)
    parser = FakeParser()
    parser.next_outcome = ParseOutcome(parsed=[_parsed("sale", "Kopi", 15_000)], failures=[])

    await RecordTransactions(parser, uow, observability=obs).execute(user_id, "raw", TODAY)

    assert obs.events == []
    assert obs.metrics == []


async def test_record_transactions_works_without_an_adapter(uow: FakeUnitOfWork) -> None:
    """Observability stays optional: two-argument construction must still run."""
    parser = FakeParser()
    parser.next_outcome = ParseOutcome(
        parsed=[], failures=[FailedSegment(raw_text="???", reason="no_amount")]
    )
    user_id = await _create_user(uow)

    result = await RecordTransactions(parser, uow).execute(user_id, "raw", TODAY)

    assert len(result.issues) == 1


# --- GenerateReport ----------------------------------------------------------


async def test_report_generated_is_logged(uow: FakeUnitOfWork, obs: FakeObservability) -> None:
    user_id = await _create_user(uow)
    use_case = GenerateReport(
        uow, FakeRateLimiter(), FakeReportRenderer(b"%PDF-1.7 fake%"), observability=obs
    )

    await use_case.execute(user_id, TODAY, TODAY, "Laporan Harian")

    assert len(obs.events) == 1
    event = obs.events[0]
    assert event.level == "info"
    assert event.message == "report_generated"
    assert event.fields["user_id"] == user_id
    assert event.fields["period_label"] == "Laporan Harian"
    assert event.fields["start"] == TODAY.isoformat()
    assert event.fields["pdf_bytes"] == len(b"%PDF-1.7 fake%")
    assert obs.exceptions == []


async def test_render_failure_is_logged_as_an_exception_and_still_raises(
    uow: FakeUnitOfWork, obs: FakeObservability
) -> None:
    user_id = await _create_user(uow)
    boom = RuntimeError("fpdf2 exploded")

    class ExplodingRenderer(FakeReportRenderer):
        async def render_pdf(self, *args: object, **kwargs: object) -> bytes:
            raise boom

    use_case = GenerateReport(uow, FakeRateLimiter(), ExplodingRenderer(), observability=obs)

    with pytest.raises(RuntimeError):
        await use_case.execute(user_id, TODAY, TODAY, "Laporan Harian")

    assert len(obs.exceptions) == 1
    logged = obs.exceptions[0]
    assert logged.error is boom
    assert logged.context == {
        "use_case": "generate_report",
        "user_id": user_id,
        "start": TODAY.isoformat(),
        "end": TODAY.isoformat(),
        "period_label": "Laporan Harian",
    }
    # The failure still reaches the caller — telemetry never swallows it.
    assert obs.events == []


async def test_rate_limited_report_emits_nothing(
    uow: FakeUnitOfWork, obs: FakeObservability
) -> None:
    """RateLimited is an expected outcome, not an incident."""
    user_id = await _create_user(uow)
    use_case = GenerateReport(
        uow, FakeRateLimiter(), FakeReportRenderer(), max_per_user_hour=1, observability=obs
    )

    await use_case.execute(user_id, TODAY, TODAY)
    obs.events.clear()
    with pytest.raises(Exception):  # noqa: B017 - RateLimited, asserted elsewhere
        await use_case.execute(user_id, TODAY, TODAY)

    assert obs.events == []
    assert obs.exceptions == []
