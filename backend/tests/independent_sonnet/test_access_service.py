"""can_access_patient és DoctorPatient összerendelés — F2, F3, a 10-11. pont.

2026-10-10: a specifikáció módosult (a másik független tesztíró leletei
alapján) — a korábbi „legfeljebb egy aktív (valid_to IS NULL) összerendelés"
részleges egyedi index helyett most egy EXCLUDE-kényszer (GiST, tstzrange
átfedés) tiltja az ÁTFEDŐ [valid_from, valid_to) időszakokat ugyanarra az
orvos-beteg párra (ez a korábbi szabályt is lefedi), és egy új CHECK
(`valid_to IS NULL OR valid_to > valid_from`) tiltja a fordított/nulla hosszú
időszakot. Az eredeti tesztek változatlanul érvényesek (mindig explicit
valid_from/valid_to-t adnak meg), de új teszteket vettem fel kifejezetten az
átfedés-kényszerre (lezárt, nem teljesen nyitott időszakok átfedésére is) és
az új CHECK-re.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.access import can_access_patient
from tests.independent_sonnet.helpers import assign, make_admin, make_doctor, make_patient

NOW = datetime.now(UTC)


def test_patient_can_access_own_data(db: Session) -> None:
    patient = make_patient(db, email="sajat@example.com")

    assert can_access_patient(db, patient, patient.patient_profile.id) is True


def test_patient_cannot_access_other_patient_data(db: Session) -> None:
    patient_a = make_patient(db, email="beteg-a@example.com")
    patient_b = make_patient(db, email="beteg-b@example.com")

    assert can_access_patient(db, patient_a, patient_b.patient_profile.id) is False


def test_doctor_with_active_assignment_can_access(db: Session) -> None:
    doctor = make_doctor(db, email="orvos-aktiv@example.com")
    patient = make_patient(db, email="beteg-aktiv@example.com")
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=1),
        valid_to=None,
    )

    assert can_access_patient(db, doctor, patient.patient_profile.id) is True


def test_doctor_without_assignment_cannot_access(db: Session) -> None:
    doctor = make_doctor(db, email="orvos-nincs@example.com")
    patient = make_patient(db, email="beteg-nincs@example.com")

    assert can_access_patient(db, doctor, patient.patient_profile.id) is False


def test_doctor_access_ends_immediately_when_assignment_closed(db: Session) -> None:
    doctor = make_doctor(db, email="orvos-lezart@example.com")
    patient = make_patient(db, email="beteg-lezart@example.com")
    link = assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=5),
        valid_to=None,
    )

    assert can_access_patient(db, doctor, patient.patient_profile.id) is True

    link.valid_to = NOW - timedelta(minutes=1)
    db.commit()

    assert can_access_patient(db, doctor, patient.patient_profile.id) is False


def test_doctor_access_opens_immediately_when_assignment_created(db: Session) -> None:
    doctor = make_doctor(db, email="orvos-uj@example.com")
    patient = make_patient(db, email="beteg-uj@example.com")

    assert can_access_patient(db, doctor, patient.patient_profile.id) is False

    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW,
        valid_to=None,
    )

    assert can_access_patient(db, doctor, patient.patient_profile.id) is True


def test_doctor_future_assignment_does_not_grant_access_yet(db: Session) -> None:
    """Jóváhagyás alatt: a jövőre időzített összerendelés még nem ad hozzáférést."""
    doctor = make_doctor(db, email="orvos-jovo@example.com")
    patient = make_patient(db, email="beteg-jovo@example.com")
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW + timedelta(days=1),
        valid_to=None,
    )

    assert can_access_patient(db, doctor, patient.patient_profile.id) is False


def test_doctor_past_closed_assignment_does_not_grant_access(db: Session) -> None:
    doctor = make_doctor(db, email="orvos-regi@example.com")
    patient = make_patient(db, email="beteg-regi@example.com")
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=10),
        valid_to=NOW - timedelta(days=5),
    )

    assert can_access_patient(db, doctor, patient.patient_profile.id) is False


def test_admin_never_accesses_patient_data(db: Session) -> None:
    """Jóváhagyás alatt: az admin soha nem fér hozzá betegadathoz."""
    admin = make_admin(db, email="admin-nincs-hozzaferes@example.com")
    patient = make_patient(db, email="beteg-admin-teszt@example.com")

    assert can_access_patient(db, admin, patient.patient_profile.id) is False


def test_disabled_doctor_loses_access_despite_active_assignment(db: Session) -> None:
    doctor = make_doctor(db, email="orvos-letiltott@example.com")
    patient = make_patient(db, email="beteg-orvos-letiltott@example.com")
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=1),
        valid_to=None,
    )
    assert can_access_patient(db, doctor, patient.patient_profile.id) is True

    doctor.is_active = False
    db.commit()

    assert can_access_patient(db, doctor, patient.patient_profile.id) is False


def test_disabled_patient_loses_access_to_own_data(db: Session) -> None:
    patient = make_patient(db, email="beteg-sajat-letiltott@example.com")
    patient.is_active = False
    db.commit()

    assert can_access_patient(db, patient, patient.patient_profile.id) is False


def test_closing_one_assignment_allows_new_active_one(db: Session) -> None:
    doctor = make_doctor(db, email="orvos-ujra@example.com")
    patient = make_patient(db, email="beteg-ujra@example.com")
    old = assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=30),
        valid_to=None,
    )
    old.valid_to = NOW - timedelta(days=1)
    db.commit()

    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW,
        valid_to=None,
    )

    assert can_access_patient(db, doctor, patient.patient_profile.id) is True


def test_two_simultaneous_active_assignments_rejected_by_db(db: Session) -> None:
    """Egy orvos-beteg párnak legfeljebb egy aktív összerendelése lehet (DB-kényszer)."""
    doctor = make_doctor(db, email="orvos-dupla@example.com")
    patient = make_patient(db, email="beteg-dupla@example.com")
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=1),
        valid_to=None,
    )

    with pytest.raises(IntegrityError):
        assign(
            db,
            doctor_id=doctor.doctor_profile.id,
            patient_id=patient.patient_profile.id,
            valid_from=NOW,
            valid_to=None,
        )


# --- Új tesztek: átfedés-kényszer és az új CHECK (2026-10-10) ---


def test_overlapping_closed_periods_rejected_by_db(db: Session) -> None:
    """Két LEZÁRT (egyik sem nyitott végű), de időben átfedő összerendelés is
    ütközik az EXCLUDE-kényszerrel — nem csak a két teljesen nyitott eset."""
    doctor = make_doctor(db, email="orvos-atfedo@example.com")
    patient = make_patient(db, email="beteg-atfedo@example.com")
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=30),
        valid_to=NOW - timedelta(days=10),
    )

    with pytest.raises(IntegrityError):
        assign(
            db,
            doctor_id=doctor.doctor_profile.id,
            patient_id=patient.patient_profile.id,
            valid_from=NOW - timedelta(days=15),
            valid_to=NOW - timedelta(days=5),
        )


def test_back_to_back_periods_do_not_overlap(db: Session) -> None:
    """[valid_from, valid_to) félig nyitott: ha az egyik záróideje pontosan a
    másik kezdete, az nem átfedés (nincs közös pillanat)."""
    doctor = make_doctor(db, email="orvos-egymasutan@example.com")
    patient = make_patient(db, email="beteg-egymasutan@example.com")
    boundary = NOW - timedelta(days=10)
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=NOW - timedelta(days=30),
        valid_to=boundary,
    )

    # Nem szabad IntegrityError-t dobnia.
    assign(
        db,
        doctor_id=doctor.doctor_profile.id,
        patient_id=patient.patient_profile.id,
        valid_from=boundary,
        valid_to=None,
    )


def test_valid_to_before_valid_from_rejected_by_check(db: Session) -> None:
    """Új CHECK: valid_to IS NULL OR valid_to > valid_from."""
    doctor = make_doctor(db, email="orvos-forditott@example.com")
    patient = make_patient(db, email="beteg-forditott@example.com")

    with pytest.raises(IntegrityError):
        assign(
            db,
            doctor_id=doctor.doctor_profile.id,
            patient_id=patient.patient_profile.id,
            valid_from=NOW,
            valid_to=NOW - timedelta(days=1),
        )


def test_valid_to_equal_to_valid_from_rejected_by_check(db: Session) -> None:
    """Nulla hosszú időszak (valid_to == valid_from) is tiltott."""
    doctor = make_doctor(db, email="orvos-nullaido@example.com")
    patient = make_patient(db, email="beteg-nullaido@example.com")

    with pytest.raises(IntegrityError):
        assign(
            db,
            doctor_id=doctor.doctor_profile.id,
            patient_id=patient.patient_profile.id,
            valid_from=NOW,
            valid_to=NOW,
        )
