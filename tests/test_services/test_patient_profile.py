from datetime import date

from backend.db.models import Patient
from backend.services.patient_profile import is_patient_profile_complete


def _patient(**values: object) -> Patient:
    defaults: dict[str, object] = {
        "id": "patient-test",
        "full_name": "Patient Test",
        "date_of_birth": date(1995, 6, 15),
        "phone": "0912345678",
        "address": "123 Đường Test, Quận 1",
        "gender": "nam",
        "height_cm": 175,
        "weight_kg": 68,
    }
    defaults.update(values)
    return Patient(**defaults)


def test_profile_requires_all_six_onboarding_fields() -> None:
    assert is_patient_profile_complete(_patient()) is True
    assert is_patient_profile_complete(_patient(height_cm=None)) is False
    assert is_patient_profile_complete(_patient(weight_kg=None)) is False
    assert is_patient_profile_complete(_patient(phone="  ")) is False
