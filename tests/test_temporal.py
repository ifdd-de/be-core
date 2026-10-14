"""The bitemporal write planner (ifdd.be.core.temporal), without a database.

Every test shows the valid time of the versions as a timeline. Years stand for
instants (``Y(2020)`` is 2020-01-01T00:00Z), "now" is 2026. ``[2020 ->`` is
open-ended, ``[2020 -> 2027)`` ends before 2027.
"""

from datetime import datetime, timezone

import pytest

from ifdd.be.core.temporal import (
    Content,
    Period,
    PeriodError,
    Version,
    plan_delete,
    plan_put,
    requested_period,
    version_at,
)


def Y(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=timezone.utc)


NOW = Y(2026)
A = Content(canonical='{"name":"A"}')
B = Content(canonical='{"name":"B"}')


def known(content: Content, start: int, end: int | None = None, cached: int = 2020) -> Version:
    """A version that is current in system time."""
    return Version(Period(Y(start), Y(end) if end else None), content, cache_created=Y(cached))


def timeline(plan) -> list[tuple[str, int, int | None]]:
    """The recorded versions as (content, start year, end year), sorted."""
    return sorted(
        (v.content.canonical, v.valid.start.year, v.valid.end.year if v.valid.end else None)
        for v in plan.record
    )


# --- Period -------------------------------------------------------------------------


def test_a_period_must_not_be_empty():
    with pytest.raises(PeriodError):
        Period(Y(2027), Y(2027))
    with pytest.raises(PeriodError):
        Period(Y(2028), Y(2027))


def test_adjacent_periods_do_not_overlap():
    """[2020 -> 2027) and [2027 -> share no instant (half-open periods)."""
    assert not Period(Y(2020), Y(2027)).overlaps(Period(Y(2027)))
    assert Period(Y(2020), Y(2028)).overlaps(Period(Y(2027)))


@pytest.mark.parametrize(
    "period, cut, expected",
    [
        # [2020 -> 2030) minus [2031 ->            : untouched
        ((2020, 2030), (2031, None), [(2020, 2030)]),
        # [2020 -> 2030) minus [2025 ->            : left part stays
        ((2020, 2030), (2025, None), [(2020, 2025)]),
        # [2020 -> 2030) minus [2010 -> 2025)      : right part stays
        ((2020, 2030), (2010, 2025), [(2025, 2030)]),
        # [2020 ->       minus [2025 -> 2027)      : a hole, two parts
        ((2020, None), (2025, 2027), [(2020, 2025), (2027, None)]),
        # [2020 -> 2030) minus [2010 ->            : nothing stays
        ((2020, 2030), (2010, None), []),
    ],
)
def test_period_minus(period, cut, expected):
    def p(pair):
        return Period(Y(pair[0]), Y(pair[1]) if pair[1] else None)

    parts = p(period).minus(p(cut))
    assert [(x.start.year, x.end.year if x.end else None) for x in parts] == expected


def test_requested_period_defaults_to_from_now_on():
    assert requested_period(None, None, NOW) == Period(NOW)
    assert requested_period(Y(2020), None, NOW) == Period(Y(2020))
    assert requested_period(None, Y(2030), NOW) == Period(NOW, Y(2030))


def test_requested_period_rejects_an_end_before_the_start():
    with pytest.raises(PeriodError):
        requested_period(Y(2030), Y(2020), NOW)


# --- PUT: new documents and idempotency ----------------------------------------------


def test_a_new_document_is_valid_from_now_on():
    """
    known:  (nothing)
    PUT A   [now ->
    result: A [now ->
    """
    plan = plan_put([], A, Period(NOW), NOW)
    assert plan.retire == ()
    assert timeline(plan) == [(A.canonical, 2026, None)]
    assert plan.record[0].cache_created == NOW


def test_writing_known_content_again_changes_nothing():
    """
    known:  A [2020 ->
    PUT A   [now ->          (already known for the whole period)
    result: unchanged, A is confirmed
    """
    current = [known(A, 2020)]
    plan = plan_put(current, A, Period(NOW), NOW)
    assert not plan.changes_anything
    assert plan.confirm == tuple(current)


def test_only_the_versions_a_write_repeats_are_confirmed():
    """
    known:  A [2020 -> 2027)   A [2027 ->
    PUT A   [2028 ->           (repeats only the second version)
    result: unchanged, only A [2027 -> is confirmed
    """
    past, later = known(A, 2020, 2027), known(A, 2027)
    plan = plan_put([past, later], A, Period(Y(2028)), NOW)
    assert plan.confirm == (later,)


def test_a_change_confirms_nothing():
    plan = plan_put([known(A, 2020)], B, Period(NOW), NOW)
    assert plan.changes_anything and plan.confirm == ()


def test_known_content_split_over_adjacent_versions_is_still_known():
    """
    known:  A [2020 -> 2026)  A [2026 ->      (left over from an earlier write)
    PUT A   [2020 ->
    result: unchanged - the two versions together cover the period
    """
    current = [known(A, 2020, 2026), known(A, 2026)]
    assert not plan_put(current, A, Period(Y(2020)), NOW).changes_anything


def test_a_gap_between_equal_versions_is_a_change():
    """
    known:  A [2020 -> 2024)        A [2026 ->
    PUT A   [2020 ->               (2024 -> 2026 is not known yet)
    result: A [2020 ->
    """
    current = [known(A, 2020, 2024), known(A, 2026)]
    plan = plan_put(current, A, Period(Y(2020)), NOW)
    assert len(plan.retire) == 2
    assert timeline(plan) == [(A.canonical, 2020, None)]


def test_a_longer_period_with_the_same_content_is_a_change():
    """
    known:  A [2025 ->
    PUT A   [2020 ->
    result: A [2020 ->
    """
    plan = plan_put([known(A, 2025)], A, Period(Y(2020)), NOW)
    assert timeline(plan) == [(A.canonical, 2020, None)]


def test_a_shorter_period_with_the_same_content_changes_nothing():
    """A PUT says what holds in its period, nothing about the time after it.

    known:  A [2020 ->
    PUT A   [2020 -> 2030)
    result: unchanged. To end the validity at 2030, DELETE [2030 ->.
    """
    assert not plan_put([known(A, 2020)], A, Period(Y(2020), Y(2030)), NOW).changes_anything


def test_new_source_dates_are_a_change():
    """c_created / c_modified belong to the content."""
    newer = Content(canonical=A.canonical, modified=Y(2026))
    plan = plan_put([known(A, 2020)], newer, Period(NOW), NOW)
    assert plan.changes_anything


# --- PUT: replacing a portion of the valid time ------------------------------------


def test_a_change_from_now_on_keeps_the_past():
    """
    known:  A [2020 ->
    PUT B   [now ->
    result: A [2020 -> now)  B [now ->
    """
    current = [known(A, 2020)]
    plan = plan_put(current, B, Period(NOW), NOW)
    assert plan.retire == tuple(current)
    assert timeline(plan) == [(A.canonical, 2020, 2026), (B.canonical, 2026, None)]


def test_a_planned_change_keeps_the_present():
    """
    known:  A [2020 ->
    PUT B   [2027 ->
    result: A [2020 -> 2027)  B [2027 ->
    """
    plan = plan_put([known(A, 2020)], B, Period(Y(2027)), NOW)
    assert timeline(plan) == [(A.canonical, 2020, 2027), (B.canonical, 2027, None)]


def test_a_change_in_the_middle_splits_the_version():
    """
    known:  A [2020 ->
    PUT B   [2027 -> 2028)
    result: A [2020 -> 2027)  B [2027 -> 2028)  A [2028 ->
    """
    plan = plan_put([known(A, 2020)], B, Period(Y(2027), Y(2028)), NOW)
    assert timeline(plan) == [
        (A.canonical, 2020, 2027),
        (A.canonical, 2028, None),
        (B.canonical, 2027, 2028),
    ]


def test_a_write_across_several_versions_replaces_all_of_them():
    """
    known:  A [2020 -> 2025)  B [2025 -> 2030)  A [2030 ->
    PUT B   [2022 -> 2032)
    result: A [2020 -> 2022)  B [2022 -> 2032)  A [2032 ->
    """
    current = [known(A, 2020, 2025), known(B, 2025, 2030), known(A, 2030)]
    plan = plan_put(current, B, Period(Y(2022), Y(2032)), NOW)
    assert len(plan.retire) == 3
    assert timeline(plan) == [
        (A.canonical, 2020, 2022),
        (A.canonical, 2032, None),
        (B.canonical, 2022, 2032),
    ]


def test_a_write_into_a_gap_retires_nothing():
    """
    known:  A [2020 -> 2025)
    PUT B   [2030 ->
    result: A [2020 -> 2025) (untouched)  B [2030 ->
    """
    plan = plan_put([known(A, 2020, 2025)], B, Period(Y(2030)), NOW)
    assert plan.retire == ()
    assert timeline(plan) == [(B.canonical, 2030, None)]


def test_first_cached_is_kept_across_versions():
    """c_cacheCreated is the first time the document was stored, whatever the period."""
    current = [known(A, 2020, 2027, cached=2021), known(B, 2027, cached=2023)]
    plan = plan_put(current, B, Period(NOW), NOW)
    written = next(v for v in plan.record if v.valid.start == NOW)
    assert written.cache_created == Y(2021)
    remainder = next(v for v in plan.record if v.valid.start == Y(2020))
    assert remainder.cache_created == Y(2021)


# --- DELETE --------------------------------------------------------------------------


def test_deleting_from_now_on_keeps_the_past():
    """
    known:  A [2020 ->
    DELETE  [now ->
    result: A [2020 -> now)
    """
    plan = plan_delete([known(A, 2020)], Period(NOW))
    assert timeline(plan) == [(A.canonical, 2020, 2026)]


def test_deleting_a_portion_leaves_a_hole():
    """
    known:  A [2020 ->
    DELETE  [2027 -> 2028)
    result: A [2020 -> 2027)  A [2028 ->
    """
    plan = plan_delete([known(A, 2020)], Period(Y(2027), Y(2028)))
    assert timeline(plan) == [(A.canonical, 2020, 2027), (A.canonical, 2028, None)]


def test_deleting_everything_records_nothing():
    plan = plan_delete([known(A, 2020)], Period(Y(2000)))
    assert len(plan.retire) == 1 and plan.record == ()


def test_deleting_where_nothing_is_known_is_an_empty_plan():
    assert not plan_delete([known(A, 2020, 2025)], Period(Y(2030))).changes_anything


# --- PATCH base ------------------------------------------------------------------------


def test_version_at_finds_the_version_valid_at_an_instant():
    current = [known(A, 2020, 2027), known(B, 2027)]
    assert version_at(current, NOW).content == A
    assert version_at(current, Y(2027)).content == B
    assert version_at(current, Y(2019)) is None
