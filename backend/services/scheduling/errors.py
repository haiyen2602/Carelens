"""Business exceptions for the V2 dose state domain."""

from __future__ import annotations

from backend.services.prescription.errors import VmecError


class DoseOccurrenceNotFoundError(VmecError):
    """The requested V2 occurrence does not exist."""

    ma_loi = "DOSE_OCCURRENCE_NOT_FOUND"
    http_status = 404


class InvalidDoseTransitionError(VmecError):
    """The requested transition contradicts the persisted dose state."""

    ma_loi = "INVALID_DOSE_TRANSITION"
    http_status = 409


class InvalidReminderConfigurationError(VmecError):
    """Reminder offsets cannot be safely applied to the occurrence window."""

    ma_loi = "INVALID_REMINDER_CONFIGURATION"
    http_status = 422


__all__ = [
    "DoseOccurrenceNotFoundError",
    "InvalidDoseTransitionError",
    "InvalidReminderConfigurationError",
]
