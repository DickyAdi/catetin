"""Application-layer (M3) use-case tests, against fakes only — no SQLAlchemy,
no Telegram, no wall clock. Real persistence atomicity is covered by
`tests/integration/test_repositories.py`.
"""

from datetime import UTC, date, datetime

import pytest

from catetin.application.generate_report import (
    GenerateReport,
    PendingReview,
    ReportResult,
)
from catetin.application.manage_transactions import ManageTransactions
from catetin.application.onboarding import Onboarding
from catetin.application.record_transactions import RecordTransactions
from catetin.application.summarize import Summarize
from catetin.domain.errors import RateLimited
from catetin.domain.models import FailedSegment, ParsedTransaction, ParseOutcome
from tests.fakes.fake_parser import FakeParser
from tests.fakes.fake_repositories import (
    FakeRateLimiter,
    FakeReportRenderer,
    FakeUnitOfWork,
)
from tests.fakes.frozen_clock import FrozenClock

TODAY = date(2026, 8, 15)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 8, 15, 12, 0, tzinfo=UTC))


@pytest.fixture
def uow(clock: FrozenClock) -> FakeUnitOfWork:
    return FakeUnitOfWork(clock)


@pytest.fixture
def parser() -> FakeParser:
    return FakeParser()


def _parsed(
    kind: str | None,
    item: str,
    total_amount: int = 10_000,
    raw_text: str | None = None,
    occurred_on: date = TODAY,
    confidence: float = 1.0,
    flagged: bool = False,
) -> ParsedTransaction:
    return ParsedTransaction(
        kind=kind,  # type: ignore[arg-type]
        item=item,
        qty=1,
        unit_amount=None,
        total_amount=total_amount,
        occurred_on=occurred_on,
        confidence=confidence,
        raw_text=raw_text or f"{item} {total_amount}",
        flagged=flagged,
    )


async def _create_user(uow: FakeUnitOfWork, platform_user_id: str) -> int:
    onboarding = Onboarding(uow)
    user = await onboarding.get_or_create_user("telegram", platform_user_id, "Budi")
    return user.id


# --- RecordTransactions ------------------------------------------------------


async def test_record_happy_path_sale_and_expense(
    uow: FakeUnitOfWork, parser: FakeParser, clock: FrozenClock
) -> None:
    user_id = await _create_user(uow, "1001")
    parser.next_outcome = ParseOutcome(
        parsed=[
            _parsed("sale", "Ayam Geprek", 50_000),
            _parsed("expense", "Tepung", 20_000),
        ],
        failures=[],
    )
    use_case = RecordTransactions(parser, uow)

    result = await use_case.execute(user_id, "jual ayam geprek 50rb\nbeli tepung 20rb", TODAY)

    assert len(result.recorded) == 2
    assert {t.item for t in result.recorded} == {"Ayam Geprek", "Tepung"}
    assert result.issues == []
    assert result.today_total.income == 50_000
    assert result.today_total.expense == 20_000
    assert result.today_total.profit == 30_000
    assert result.today_total.count == 2


async def test_record_multi_segment_batch_commits_valid_subset_together(
    uow: FakeUnitOfWork, parser: FakeParser
) -> None:
    """Batch of 3 where one segment fails: the two valid ones are still
    committed as a single batch, and the failure is reported alongside."""
    parser.next_outcome = ParseOutcome(
        parsed=[
            _parsed("sale", "Kopi", 15_000),
            _parsed("sale", "Teh", 10_000),
        ],
        failures=[FailedSegment(raw_text="laris manis hari ini", reason="no_amount")],
    )
    user_id = await _create_user(uow, "1002")
    use_case = RecordTransactions(parser, uow)

    result = await use_case.execute(user_id, "irrelevant raw text", TODAY)

    assert {t.item for t in result.recorded} == {"Kopi", "Teh"}
    assert len(result.issues) == 1
    assert result.issues[0].reason == "no_amount"

    # Confirm the valid subset is actually visible afterward (i.e. committed).
    manage = ManageTransactions(uow)
    recent = await manage.list_recent(user_id)
    assert {t.item for t in recent} == {"Kopi", "Teh"}


async def test_record_parse_failure_returns_reason(
    uow: FakeUnitOfWork, parser: FakeParser
) -> None:
    parser.next_outcome = ParseOutcome(
        parsed=[], failures=[FailedSegment(raw_text="laris manis hari ini", reason="no_amount")]
    )
    user_id = await _create_user(uow, "1003")
    use_case = RecordTransactions(parser, uow)

    result = await use_case.execute(user_id, "laris manis hari ini", TODAY)

    assert result.recorded == []
    assert len(result.issues) == 1
    assert result.issues[0].reason == "no_amount"
    assert result.issues[0].raw_text == "laris manis hari ini"


async def test_record_ambiguous_kind_is_reported_not_persisted(
    uow: FakeUnitOfWork, parser: FakeParser
) -> None:
    parser.next_outcome = ParseOutcome(
        parsed=[_parsed(None, "Ayam", 50_000, raw_text="ayam 50rb")], failures=[]
    )
    user_id = await _create_user(uow, "1004")
    use_case = RecordTransactions(parser, uow)

    result = await use_case.execute(user_id, "ayam 50rb", TODAY)

    assert result.recorded == []
    assert len(result.issues) == 1
    assert result.issues[0].reason == "ambiguous_kind"
    assert result.issues[0].raw_text == "ayam 50rb"


# --- Summarize ----------------------------------------------------------------


async def test_summarize_today_aggregates_income_expense_profit_count(
    uow: FakeUnitOfWork, parser: FakeParser
) -> None:
    user_id = await _create_user(uow, "2001")
    parser.next_outcome = ParseOutcome(
        parsed=[
            _parsed("sale", "Kopi", 15_000),
            _parsed("sale", "Teh", 10_000),
            _parsed("expense", "Gula", 5_000),
        ],
        failures=[],
    )
    await RecordTransactions(parser, uow).execute(user_id, "irrelevant", TODAY)

    summary = await Summarize(uow).today(user_id, TODAY)

    assert summary.income == 25_000
    assert summary.expense == 5_000
    assert summary.profit == 20_000
    assert summary.count == 3


async def test_summarize_week_returns_day_totals(
    uow: FakeUnitOfWork, parser: FakeParser
) -> None:
    user_id = await _create_user(uow, "2002")
    parser.next_outcome = ParseOutcome(
        parsed=[_parsed("sale", "Kopi", 15_000, occurred_on=date(2026, 8, 10))], failures=[]
    )
    await RecordTransactions(parser, uow).execute(user_id, "irrelevant", date(2026, 8, 10))

    day_totals = await Summarize(uow).week(user_id, TODAY)

    assert any(d.date == "2026-08-10" and d.income == 15_000 for d in day_totals)


# --- ManageTransactions ---------------------------------------------------


async def test_batal_removes_last_by_created_at_and_id_tiebreaker(
    uow: FakeUnitOfWork, parser: FakeParser
) -> None:
    user_id = await _create_user(uow, "3001")
    parser.next_outcome = ParseOutcome(
        parsed=[_parsed("sale", "Pertama", 10_000)], failures=[]
    )
    await RecordTransactions(parser, uow).execute(user_id, "pertama", TODAY)
    parser.next_outcome = ParseOutcome(parsed=[_parsed("sale", "Terakhir", 20_000)], failures=[])
    await RecordTransactions(parser, uow).execute(user_id, "terakhir", TODAY)

    manage = ManageTransactions(uow)
    removed_first = await manage.cancel_last(user_id)
    assert removed_first is not None
    assert removed_first.item == "Terakhir"

    # Second /batal in a row removes the next-most-recent, not a no-op.
    removed_second = await manage.cancel_last(user_id)
    assert removed_second is not None
    assert removed_second.item == "Pertama"

    remaining = await manage.list_recent(user_id)
    assert remaining == []


# --- GenerateReport / rate limiting ----------------------------------------


async def test_generate_report_rate_limits_after_five_per_hour(
    uow: FakeUnitOfWork,
) -> None:
    user_id = await _create_user(uow, "4001")
    limiter = FakeRateLimiter()
    renderer = FakeReportRenderer()
    use_case = GenerateReport(uow, limiter, renderer, max_per_user_hour=5)

    for _ in range(5):
        result = await use_case.execute(user_id, TODAY, TODAY)
        assert result.pdf_bytes == b"%PDF-fake%"

    with pytest.raises(RateLimited):
        await use_case.execute(user_id, TODAY, TODAY)

    assert renderer.calls == 5


async def test_generate_report_passes_business_name_period_label_and_top_items(
    uow: FakeUnitOfWork,
) -> None:
    user_id = await _create_user(uow, "4002")
    async with uow as u:
        user = await u.users.get_by_id(user_id)
        assert user is not None
        u._users[user_id] = user.model_copy(update={"business_name": "Warung Bu Rina"})
        await u.transactions.add(
            user_id, _parsed("sale", "Ayam Geprek", 50_000, occurred_on=TODAY)
        )
    limiter = FakeRateLimiter()
    renderer = FakeReportRenderer()
    use_case = GenerateReport(uow, limiter, renderer)

    await use_case.execute(user_id, TODAY, TODAY, period_label="Laporan 7 Hari Terakhir")

    assert renderer.last_business_name == "Warung Bu Rina"
    assert renderer.last_period_label == "Laporan 7 Hari Terakhir"
    assert renderer.last_item_totals is not None
    assert renderer.last_item_totals[0].item == "Ayam Geprek"


# --- Onboarding -------------------------------------------------------------


async def test_generate_report_direct_renders_when_nothing_flagged(
    uow: FakeUnitOfWork,
) -> None:
    user_id = await _create_user(uow, "4003")
    async with uow as u:
        await u.transactions.add(user_id, _parsed("sale", "Ayam", 50_000, occurred_on=TODAY))
    limiter = FakeRateLimiter()
    renderer = FakeReportRenderer()
    use_case = GenerateReport(uow, limiter, renderer)

    result = await use_case.execute(user_id, TODAY, TODAY)

    assert isinstance(result, ReportResult)
    assert renderer.calls == 1


async def test_generate_report_returns_pending_review_when_flagged_present(
    uow: FakeUnitOfWork,
) -> None:
    user_id = await _create_user(uow, "4004")
    async with uow as u:
        await u.transactions.add(user_id, _parsed("sale", "Ayam", 50_000, occurred_on=TODAY))
        await u.transactions.add(
            user_id,
            _parsed("sale", "Dapet Duit", 10_000, occurred_on=TODAY, flagged=True),
        )
    limiter = FakeRateLimiter()
    renderer = FakeReportRenderer()
    use_case = GenerateReport(uow, limiter, renderer)

    result = await use_case.execute(user_id, TODAY, TODAY, period_label="Laporan")

    assert isinstance(result, PendingReview)
    assert len(result.flagged_items) == 1
    assert result.flagged_items[0].item == "Dapet Duit"
    assert result.summary.income == 60_000  # flag != exclude, still counted
    assert renderer.calls == 0  # no render happened yet


async def test_generate_report_exclude_flagged_then_render_is_clean(
    uow: FakeUnitOfWork,
) -> None:
    user_id = await _create_user(uow, "4005")
    async with uow as u:
        await u.transactions.add(user_id, _parsed("sale", "Ayam", 50_000, occurred_on=TODAY))
        await u.transactions.add(
            user_id,
            _parsed("sale", "Dapet Duit", 10_000, occurred_on=TODAY, flagged=True),
        )
    limiter = FakeRateLimiter()
    renderer = FakeReportRenderer()
    use_case = GenerateReport(uow, limiter, renderer)

    pending = await use_case.execute(user_id, TODAY, TODAY)
    assert isinstance(pending, PendingReview)

    excluded_count = await use_case.exclude_flagged(user_id, TODAY, TODAY)
    assert excluded_count == 1

    result = await use_case.render(user_id, TODAY, TODAY)
    assert result.summary.income == 50_000
    assert renderer.calls == 1


async def test_generate_report_keep_renders_with_everything(
    uow: FakeUnitOfWork,
) -> None:
    user_id = await _create_user(uow, "4006")
    async with uow as u:
        await u.transactions.add(user_id, _parsed("sale", "Ayam", 50_000, occurred_on=TODAY))
        await u.transactions.add(
            user_id,
            _parsed("sale", "Dapet Duit", 10_000, occurred_on=TODAY, flagged=True),
        )
    limiter = FakeRateLimiter()
    renderer = FakeReportRenderer()
    use_case = GenerateReport(uow, limiter, renderer)

    pending = await use_case.execute(user_id, TODAY, TODAY)
    assert isinstance(pending, PendingReview)

    result = await use_case.render(user_id, TODAY, TODAY)
    assert result.summary.income == 60_000  # "Tetap masukkan" — nothing excluded
    assert renderer.calls == 1


async def test_generate_report_rate_limit_checked_once_before_review_gate(
    uow: FakeUnitOfWork,
) -> None:
    """NFR / FR-2: the rate-limit check happens on the initial `execute()`
    call, not again on the `render()` that follows a review decision."""
    user_id = await _create_user(uow, "4007")
    async with uow as u:
        await u.transactions.add(
            user_id,
            _parsed("sale", "Dapet Duit", 10_000, occurred_on=TODAY, flagged=True),
        )
    limiter = FakeRateLimiter()
    renderer = FakeReportRenderer()
    use_case = GenerateReport(uow, limiter, renderer, max_per_user_hour=1)

    pending = await use_case.execute(user_id, TODAY, TODAY)
    assert isinstance(pending, PendingReview)

    # A second execute() would now be rate-limited, but render() (used after
    # the user's review decision) does not re-check the limiter.
    result = await use_case.render(user_id, TODAY, TODAY)
    assert result.summary.income == 10_000

    with pytest.raises(RateLimited):
        await use_case.execute(user_id, TODAY, TODAY)


# --- RecordTransactions.confirm — "Bukan Usaha" (FR-3) ----------------------


async def test_confirm_bukan_usaha_records_excluded_and_not_flagged(
    uow: FakeUnitOfWork,
) -> None:
    user_id = await _create_user(uow, "4501")
    parsed = _parsed(None, "Gajian", 2_000_000, flagged=True)
    use_case = RecordTransactions(FakeParser(), uow)

    resolved = parsed.model_copy(update={"kind": "sale", "flagged": False})
    tx = await use_case.confirm(user_id, resolved, excluded_from_report=True)

    assert tx.kind == "sale"
    assert tx.flagged is False
    assert tx.excluded_from_report is True

    summary = await Summarize(uow).today(user_id, TODAY)
    assert summary.income == 0  # excluded — not in the report total
    assert summary.count == 0

    manage = ManageTransactions(uow)
    recent = await manage.list_recent(user_id)
    assert len(recent) == 1  # still visible in /list (audit completeness)


async def test_get_or_create_user_twice_returns_same_user(uow: FakeUnitOfWork) -> None:
    onboarding = Onboarding(uow)

    first = await onboarding.get_or_create_user("telegram", "5001", "Budi")
    second = await onboarding.get_or_create_user("telegram", "5001", "Budi (lagi)")

    assert first.id == second.id
    assert second.display_name == "Budi"  # not re-created, original name kept


async def test_toggle_digest_and_set_timezone(uow: FakeUnitOfWork) -> None:
    onboarding = Onboarding(uow)
    user = await onboarding.get_or_create_user("telegram", "5002")

    off = await onboarding.toggle_digest(user.id, False)
    assert off.digest_enabled is False

    with_tz = await onboarding.set_timezone(user.id, "Asia/Makassar")
    assert with_tz.timezone == "Asia/Makassar"


# --- Cross-user isolation ---------------------------------------------------


async def test_cross_user_isolation_at_use_case_level(
    uow: FakeUnitOfWork, parser: FakeParser
) -> None:
    user_a = await _create_user(uow, "6001")
    user_b = await _create_user(uow, "6002")

    parser.next_outcome = ParseOutcome(parsed=[_parsed("sale", "Milik-A", 100_000)], failures=[])
    await RecordTransactions(parser, uow).execute(user_a, "milik a", TODAY)

    parser.next_outcome = ParseOutcome(parsed=[_parsed("sale", "Milik-B", 999_000)], failures=[])
    await RecordTransactions(parser, uow).execute(user_b, "milik b", TODAY)

    summary_a = await Summarize(uow).today(user_a, TODAY)
    summary_b = await Summarize(uow).today(user_b, TODAY)

    assert summary_a.income == 100_000
    assert summary_b.income == 999_000

    manage = ManageTransactions(uow)
    a_list = await manage.list_recent(user_a)
    assert [t.item for t in a_list] == ["Milik-A"]
