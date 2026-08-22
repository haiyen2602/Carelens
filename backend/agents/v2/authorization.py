"""Compatibility import for the server-side Agent authorization boundary.

The Agent package intentionally performs no ORM or database access.  The
implementation belongs to the application service layer.
"""

from backend.services.agent_authorization import require_agent_patient_access

__all__ = ["require_agent_patient_access"]
