"""Fail-closed contracts for external event-topology validation."""

from .contracts import (
    AdapterAssessment,
    CanonicalEvent,
    Compatibility,
    DatasetShape,
    ExternalDatasetAdapter,
    LandmarkRecord,
    assess_shape,
    validate_event_chain,
    validate_landmark_record,
)

__all__ = [
    "AdapterAssessment",
    "CanonicalEvent",
    "Compatibility",
    "DatasetShape",
    "ExternalDatasetAdapter",
    "LandmarkRecord",
    "assess_shape",
    "validate_event_chain",
    "validate_landmark_record",
]
