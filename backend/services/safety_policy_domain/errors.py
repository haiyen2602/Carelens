"""Business errors for V2 medication safety policy persistence."""

from __future__ import annotations

from backend.services.prescription.errors import VmecError


class DoseSafetyOccurrenceNotFoundError(VmecError):
    """The occurrence requested for assessment does not exist."""

    ma_loi = "DOSE_SAFETY_OCCURRENCE_NOT_FOUND"
    http_status = 404


class DoseSafetyStateError(VmecError):
    """Only a terminal MISSED or DELAYED occurrence can be assessed."""

    ma_loi = "DOSE_SAFETY_INVALID_STATE"
    http_status = 409


class LegacyPolicySeedError(VmecError):
    """Legacy risk input cannot be safely represented as a category fallback."""

    ma_loi = "LEGACY_POLICY_SEED_INVALID"
    http_status = 422


class SafetyAssessmentNotFoundError(VmecError):
    """The requested durable safety assessment does not exist."""

    ma_loi = "SAFETY_ASSESSMENT_NOT_FOUND"
    http_status = 404


__all__ = [
    "DoseSafetyOccurrenceNotFoundError",
    "DoseSafetyStateError",
    "LegacyPolicySeedError",
    "SafetyAssessmentNotFoundError",
]
