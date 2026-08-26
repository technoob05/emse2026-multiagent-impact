"""Canonical schema and temporal gates for external validation datasets.

This module deliberately contains no downloader and no source-specific parser.
An adapter must first normalize a source into the declared pull-request and
event fields.  Capability assessment then fails closed when a paper construct
cannot be observed or when a frozen observation boundary is unavailable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class Compatibility(StrEnum):
    """How much of the event-anchored design a source can reproduce."""

    FULL = "FULL"
    CONDITIONAL = "CONDITIONAL"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasetShape:
    """Columns available after source-specific normalization."""

    name: str
    pull_request_columns: frozenset[str]
    event_columns: frozenset[str]
    version_pinned: bool
    fixed_observation_cutoff: bool
    independent_from_primary: bool

    @classmethod
    def from_columns(
        cls,
        *,
        name: str,
        pull_request_columns: Iterable[str],
        event_columns: Iterable[str],
        version_pinned: bool,
        fixed_observation_cutoff: bool,
        independent_from_primary: bool,
    ) -> DatasetShape:
        return cls(
            name=name,
            pull_request_columns=frozenset(pull_request_columns),
            event_columns=frozenset(event_columns),
            version_pinned=version_pinned,
            fixed_observation_cutoff=fixed_observation_cutoff,
            independent_from_primary=independent_from_primary,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterAssessment:
    dataset: str
    status: Compatibility
    constructs: Mapping[str, bool]
    missing_fields: Mapping[str, tuple[str, ...]]
    warnings: tuple[str, ...]


_CONSTRUCT_FIELDS: Mapping[str, tuple[frozenset[str], frozenset[str]]] = {
    "pr_trigger": (
        frozenset({"pr_id", "repo_id", "author_product", "created_at"}),
        frozenset({"pr_id", "event_id", "event_kind", "event_at", "product_label"}),
    ),
    "exact_reply_parent": (
        frozenset(),
        frozenset({"event_id", "parent_event_id"}),
    ),
    "review_batch": (
        frozenset(),
        frozenset({"review_batch_id"}),
    ),
    "public_actor_product": (
        frozenset(),
        frozenset({"actor_login", "actor_kind", "product_label"}),
    ),
    "later_state": (
        frozenset({"pr_id", "created_at", "closed_at", "merged_at"}),
        frozenset({"pr_id", "event_at"}),
    ),
}


def assess_shape(shape: DatasetShape) -> AdapterAssessment:
    """Assess observability without treating proxy fields as equivalent."""

    constructs: dict[str, bool] = {}
    missing: dict[str, tuple[str, ...]] = {}
    for construct, (pr_required, event_required) in _CONSTRUCT_FIELDS.items():
        absent = sorted(
            {f"pull_request.{name}" for name in pr_required - shape.pull_request_columns}
            | {f"event.{name}" for name in event_required - shape.event_columns}
        )
        constructs[construct] = not absent
        if absent:
            missing[construct] = tuple(absent)

    temporal_safe = shape.version_pinned and shape.fixed_observation_cutoff
    constructs["leakage_safe_boundary"] = temporal_safe
    boundary_missing: list[str] = []
    if not shape.version_pinned:
        boundary_missing.append("metadata.version_pin")
    if not shape.fixed_observation_cutoff:
        boundary_missing.append("metadata.fixed_observation_cutoff")
    if boundary_missing:
        missing["leakage_safe_boundary"] = tuple(boundary_missing)

    full = all(constructs.values())
    minimum = all(
        constructs[name]
        for name in ("pr_trigger", "public_actor_product", "later_state", "leakage_safe_boundary")
    )
    status = (
        Compatibility.FULL
        if full
        else Compatibility.CONDITIONAL
        if minimum
        else Compatibility.INCOMPATIBLE
    )
    warnings: list[str] = []
    if not shape.independent_from_primary:
        warnings.append(
            "The source overlaps the primary corpus; it can test portability across "
            "versions, not independent external validity."
        )
    if not constructs["exact_reply_parent"]:
        warnings.append(
            "Co-presence or temporal succession cannot substitute for an exact addressed edge."
        )
    if not constructs["review_batch"]:
        warnings.append(
            "Review rows cannot be de-batched; one API review may appear to answer itself."
        )
    if not temporal_safe:
        warnings.append(
            "Outcome estimates are blocked until version and observation cutoff are frozen."
        )
    return AdapterAssessment(
        dataset=shape.name,
        status=status,
        constructs=dict(constructs),
        missing_fields=dict(missing),
        warnings=tuple(warnings),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalEvent:
    pr_id: int | str
    event_id: int | str
    event_kind: str
    event_at: datetime
    actor_login: str
    actor_kind: str
    product_label: str | None
    parent_event_id: int | str | None = None
    review_batch_id: int | str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LandmarkRecord:
    pr_id: int | str
    pr_created_at: datetime
    trigger_at: datetime
    landmark_at: datetime
    observation_cutoff: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def validate_event_chain(
    trigger: CanonicalEvent,
    response: CanonicalEvent,
    *,
    require_exact_parent: bool = True,
) -> tuple[str, ...]:
    """Return violations for one proposed trigger-response edge."""

    _aware(trigger.event_at, "trigger.event_at")
    _aware(response.event_at, "response.event_at")
    violations: list[str] = []
    if trigger.pr_id != response.pr_id:
        violations.append("cross_pr_link")
    if response.event_at <= trigger.event_at:
        violations.append("non_increasing_event_time")
    if require_exact_parent and response.parent_event_id != trigger.event_id:
        violations.append("not_exact_parent_reply")
    if (
        trigger.review_batch_id is not None
        and response.review_batch_id == trigger.review_batch_id
        and response.event_kind == "submitted_review"
    ):
        violations.append("same_review_batch")
    return tuple(violations)


def validate_landmark_record(record: LandmarkRecord) -> tuple[str, ...]:
    """Enforce risk-set and observation-window rules for later-state models."""

    for name in ("pr_created_at", "trigger_at", "landmark_at", "observation_cutoff"):
        _aware(getattr(record, name), name)
    for name in ("closed_at", "merged_at"):
        value = getattr(record, name)
        if value is not None:
            _aware(value, name)

    violations: list[str] = []
    if record.trigger_at <= record.pr_created_at:
        violations.append("trigger_not_after_pr_creation")
    if record.landmark_at <= record.trigger_at:
        violations.append("landmark_not_after_trigger")
    if record.observation_cutoff < record.landmark_at:
        violations.append("landmark_after_observation_cutoff")
    if record.closed_at is not None and record.closed_at <= record.landmark_at:
        violations.append("not_open_at_landmark")
    if record.merged_at is not None and record.merged_at <= record.landmark_at:
        violations.append("merge_not_after_landmark")
    for name in ("closed_at", "merged_at"):
        value = getattr(record, name)
        if value is not None and value > record.observation_cutoff:
            violations.append(f"{name}_after_observation_cutoff")
    return tuple(violations)


class ExternalDatasetAdapter(Protocol):
    """Minimal non-mutating interface expected from a source adapter."""

    def shape(self) -> DatasetShape: ...

    def iter_pull_requests(self) -> Iterable[Mapping[str, Any]]: ...

    def iter_events(self) -> Iterable[Mapping[str, Any]]: ...
