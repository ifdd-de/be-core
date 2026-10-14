"""Bitemporal write planning, free of any database access.

Every stored version of a node carries two half-open periods ``[start, end)``:

* **valid time** -- when the version holds in the real world. It comes from the
  source (``c_validNotBefore`` / ``c_validNotAfter``), by default
  ``[now, infinity)``.
* **system time** -- when the backend knew the version. Only the backend sets
  it: a version is recorded at ``now`` and stays current until a later write
  retires it.

This module decides *what* a write changes; :mod:`ifdd.be.core.repository`
carries the decision out. All functions work on the versions that are
current in system time for one node and context.

A write replaces only the part of the valid time it covers (as SQL:2011
``UPDATE ... FOR PORTION OF``)::

    known:    A  [2020 ------------------------------------------>
    PUT B     for [2027 ---------->2028)
    result:   A  [2020 --->2027)
              B             [2027 ---->2028)
              A                        [2028 -------------------->

The versions that overlap the written period are retired; the parts of them
outside it are recorded again as new versions; the written content gets the
written period. If the written content is already known for the whole
written period, nothing changes (idempotent writes); the versions that say it
are only *confirmed*: their ``c_cacheUpdated`` moves to the time of the write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Sequence


class PeriodError(ValueError):
    """A requested period is empty or inverted (HTTP 422)."""


@dataclass(frozen=True)
class Period:
    """A half-open time period ``[start, end)``; ``end=None`` is open-ended."""

    start: datetime
    end: Optional[datetime] = None

    def __post_init__(self):
        if self.end is not None and self.end <= self.start:
            raise PeriodError(f"empty period: start {self.start} is not before end {self.end}")

    def contains_instant(self, instant: datetime) -> bool:
        """True if ``start <= instant < end``."""
        return self.start <= instant and (self.end is None or instant < self.end)

    def overlaps(self, other: Period) -> bool:
        """True if the two periods share at least one instant."""
        return _before(self.start, other.end) and _before(other.start, self.end)

    def minus(self, other: Period) -> list[Period]:
        """The parts of this period outside ``other``: none, one or two."""
        if not self.overlaps(other):
            return [self]
        parts = []
        if self.start < other.start:
            parts.append(Period(self.start, other.start))
        if other.end is not None and _before(other.end, self.end):
            parts.append(Period(other.end, self.end))
        return parts


def _before(instant: datetime, end: Optional[datetime]) -> bool:
    """``instant < end`` where ``end=None`` is infinity."""
    return end is None or instant < end


def requested_period(
    valid_not_before: Optional[datetime],
    valid_not_after: Optional[datetime],
    now: datetime,
) -> Period:
    """The valid time a write applies to: as sent, by default ``[now, infinity)``."""
    return Period(valid_not_before or now, valid_not_after)


@dataclass(frozen=True)
class Content:
    """What a version says, without its periods and cache times.

    ``canonical`` is the expanded document serialised with sorted keys; two
    versions are equal when it and the source dates match.
    """

    canonical: str
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    # The stored representations; not part of the comparison.
    document: dict = field(default_factory=dict, compare=False)
    expanded: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Version:
    """A version that is current in system time."""

    valid: Period
    content: Content
    cache_created: datetime
    row: Any = field(default=None, compare=False)  # the ORM row, opaque here


@dataclass(frozen=True)
class NewVersion:
    """A version to record at ``now``."""

    valid: Period
    content: Content
    cache_created: datetime


@dataclass(frozen=True)
class WritePlan:
    """What a write does: retire some versions, record new ones.

    ``confirm`` lists the versions an unchanged write repeated; the write
    changes none of their content, only when they were last confirmed.
    """

    retire: tuple[Version, ...] = ()
    record: tuple[NewVersion, ...] = ()
    confirm: tuple[Version, ...] = ()

    @property
    def changes_anything(self) -> bool:
        """True if the plan retires or records a version (a confirmation does neither)."""
        return bool(self.retire or self.record)


def plan_put(
    current: Sequence[Version], content: Content, valid: Period, now: datetime
) -> WritePlan:
    """Plan writing ``content`` for the valid time ``valid``."""
    overlapping = [v for v in current if v.valid.overlaps(valid)]
    if _already_known(overlapping, content, valid):
        return WritePlan(confirm=tuple(overlapping))
    remainders = _remainders(overlapping, valid)
    written = NewVersion(valid, content, cache_created=_first_cached(current, now))
    return WritePlan(retire=tuple(overlapping), record=(*remainders, written))


def plan_delete(current: Sequence[Version], valid: Period) -> WritePlan:
    """Plan ending the node for the valid time ``valid``.

    An empty plan means there was nothing to delete in that period.
    """
    overlapping = [v for v in current if v.valid.overlaps(valid)]
    if not overlapping:
        return WritePlan()
    return WritePlan(retire=tuple(overlapping), record=tuple(_remainders(overlapping, valid)))


def version_at(current: Sequence[Version], instant: datetime) -> Optional[Version]:
    """The current version valid at ``instant`` (at most one exists)."""
    return next((v for v in current if v.valid.contains_instant(instant)), None)


def _already_known(overlapping: Sequence[Version], content: Content, valid: Period) -> bool:
    """True if every overlapping version says ``content`` and they cover ``valid``.

    Adjacent versions with the same content count together, so re-sending a
    document after a split does not split it again.
    """
    if not overlapping or any(v.content != content for v in overlapping):
        return False
    covered_until = valid.start
    for version in sorted(overlapping, key=lambda v: v.valid.start):
        if version.valid.start > covered_until:
            return False  # a gap before this version
        if version.valid.end is None:
            return True
        covered_until = max(covered_until, version.valid.end)
        if not _before(covered_until, valid.end):
            return True
    return False


def _remainders(overlapping: Sequence[Version], valid: Period) -> list[NewVersion]:
    """The parts of the overlapping versions outside ``valid``, kept as they were."""
    return [
        NewVersion(part, version.content, version.cache_created)
        for version in overlapping
        for part in version.valid.minus(valid)
    ]


def _first_cached(current: Sequence[Version], now: datetime) -> datetime:
    """When the node was first stored: kept across versions, ``now`` if new."""
    return min((v.cache_created for v in current), default=now)
