"""F2, F3, spec 10–11: can_access_patient és az orvos–beteg összerendelés."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DoctorPatient, User, UserRole
from app.services.access import active_assignment_exists, can_access_patient
from tests.independent_fable.helpers import assign, make_admin, make_doctor, make_patient


def _pid(account) -> uuid.UUID:
    assert account.user.patient_profile is not None
    return account.user.patient_profile.id


# --- 10. beteg ------------------------------------------------------------------


def test_patient_can_access_own_profile(db: Session):
    patient = make_patient(db)
    assert can_access_patient(db, patient.user, _pid(patient)) is True


def test_patient_cannot_access_other_patient(db: Session):
    a = make_patient(db)
    b = make_patient(db)
    assert can_access_patient(db, a.user, _pid(b)) is False
    assert can_access_patient(db, b.user, _pid(a)) is False


def test_patient_user_id_is_not_a_valid_patient_id(db: Session):
    """A beteg a saját User.id-jával sem fér hozzá: az azonosító a PatientProfile.id."""
    patient = make_patient(db)
    assert patient.user.id != _pid(patient)
    assert can_access_patient(db, patient.user, patient.user.id) is False


def test_patient_cannot_access_nonexistent_patient(db: Session):
    patient = make_patient(db)
    assert can_access_patient(db, patient.user, uuid.uuid4()) is False


def test_disabled_patient_cannot_access_own_profile(db: Session):
    patient = make_patient(db, active=False)
    assert can_access_patient(db, patient.user, _pid(patient)) is False


def test_patient_role_without_profile_is_denied_without_error(db: Session):
    """Inkonzisztens adat (beteg szerepkör profil nélkül): nem hiba, csak tiltás."""
    user = User(email="profilnelkul@pulse-teszt.hu", password_hash="x", role=UserRole.PATIENT)
    db.add(user)
    db.flush()
    other = make_patient(db)
    assert can_access_patient(db, user, _pid(other)) is False
    assert can_access_patient(db, user, user.id) is False


# --- 10. orvos ------------------------------------------------------------------


def test_doctor_without_assignment_is_denied(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


def test_doctor_with_open_assignment_is_allowed(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    assert can_access_patient(db, doctor.user, _pid(patient)) is True


def test_doctor_with_default_valid_from_is_allowed(db: Session):
    """A valid_from szerveroldali alapértéke (now()) is azonnal érvényes."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    db.add(
        DoctorPatient(
            doctor_id=doctor.user.doctor_profile.id, patient_id=patient.user.patient_profile.id
        )
    )
    db.flush()
    assert can_access_patient(db, doctor.user, _pid(patient)) is True


def test_doctor_assignment_with_future_valid_to_is_allowed(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient, valid_to=datetime.now(UTC) + timedelta(days=30))
    assert can_access_patient(db, doctor.user, _pid(patient)) is True


def test_doctor_assignment_expired_is_denied(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(
        db,
        doctor,
        patient,
        valid_from=datetime.now(UTC) - timedelta(days=30),
        valid_to=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


def test_doctor_assignment_scheduled_for_future_is_denied(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=datetime.now(UTC) + timedelta(minutes=5))
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


def test_doctor_assignment_with_inverted_interval_is_rejected_by_db(db: Session):
    """[MÓDOSÍTVA 2026-10-10] valid_to < valid_from: az új spec szerint már a
    beszúrást elutasítja az adatbázis (ck_doctor_patients_valid_period), így
    ilyen sor nem is jöhet létre, és hozzáférést sem adhat."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    db.commit()
    with pytest.raises(IntegrityError):
        assign(
            db,
            doctor,
            patient,
            valid_from=datetime.now(UTC) - timedelta(days=1),
            valid_to=datetime.now(UTC) - timedelta(days=2),
        )
    db.rollback()
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


def test_doctor_assignment_with_zero_length_interval_is_rejected_by_db(db: Session):
    """valid_to = valid_from: üres időszak, a CHECK (valid_to > valid_from) elutasítja."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    moment = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    db.commit()
    with pytest.raises(IntegrityError):
        assign(db, doctor, patient, valid_from=moment, valid_to=moment)
    db.rollback()


def test_doctor_only_sees_assigned_patient_not_others(db: Session):
    doctor = make_doctor(db)
    mine = make_patient(db)
    other = make_patient(db)
    assign(db, doctor, mine)
    assert can_access_patient(db, doctor.user, _pid(mine)) is True
    assert can_access_patient(db, doctor.user, _pid(other)) is False


def test_assignment_of_other_doctor_does_not_leak(db: Session):
    doctor_a = make_doctor(db)
    doctor_b = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor_a, patient)
    assert can_access_patient(db, doctor_a.user, _pid(patient)) is True
    assert can_access_patient(db, doctor_b.user, _pid(patient)) is False


def test_doctor_cannot_access_nonexistent_patient(db: Session):
    doctor = make_doctor(db)
    assert can_access_patient(db, doctor.user, uuid.uuid4()) is False


def test_doctor_cannot_use_own_profile_id_or_user_id_as_patient(db: Session):
    doctor = make_doctor(db)
    assert can_access_patient(db, doctor.user, doctor.user.id) is False
    assert can_access_patient(db, doctor.user, doctor.user.doctor_profile.id) is False


def test_disabled_doctor_with_open_assignment_is_denied(db: Session):
    doctor = make_doctor(db, active=False)
    patient = make_patient(db)
    assign(db, doctor, patient)
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


def test_doctor_disabled_after_assignment_is_denied(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    assert can_access_patient(db, doctor.user, _pid(patient)) is True
    doctor.user.is_active = False
    db.flush()
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


# --- F3: megszüntetés azonnal zár, létrejötte azonnal nyit --------------------------


def test_revoking_assignment_closes_access_immediately(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    link = assign(db, doctor, patient)
    assert can_access_patient(db, doctor.user, _pid(patient)) is True
    link.valid_to = datetime.now(UTC)
    db.flush()
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


def test_deleting_assignment_closes_access_immediately(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    link = assign(db, doctor, patient)
    db.delete(link)
    db.flush()
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


def test_creating_assignment_opens_access_immediately(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assert can_access_patient(db, doctor.user, _pid(patient)) is False
    assign(db, doctor, patient)
    assert can_access_patient(db, doctor.user, _pid(patient)) is True


def test_reassignment_after_closed_one_opens_access(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(
        db,
        doctor,
        patient,
        valid_from=datetime.now(UTC) - timedelta(days=10),
        valid_to=datetime.now(UTC) - timedelta(days=5),
    )
    assert can_access_patient(db, doctor.user, _pid(patient)) is False
    assign(db, doctor, patient)
    assert can_access_patient(db, doctor.user, _pid(patient)) is True


def test_closed_assignment_in_history_does_not_reopen_access(db: Session):
    """Több lezárt sor mellett sem nyílik ki a hozzáférés, ha nincs érvényes."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    now = datetime.now(UTC)
    assign(
        db, doctor, patient, valid_from=now - timedelta(days=30), valid_to=now - timedelta(days=20)
    )
    assign(
        db, doctor, patient, valid_from=now - timedelta(days=10), valid_to=now - timedelta(days=1)
    )
    assert can_access_patient(db, doctor.user, _pid(patient)) is False


# --- 10. admin ------------------------------------------------------------------


def test_admin_cannot_access_patient_data(db: Session):
    admin = make_admin(db)
    patient = make_patient(db)
    assert can_access_patient(db, admin.user, _pid(patient)) is False


def test_admin_cannot_access_nonexistent_patient(db: Session):
    admin = make_admin(db)
    assert can_access_patient(db, admin.user, uuid.uuid4()) is False


def test_disabled_admin_cannot_access_patient_data(db: Session):
    admin = make_admin(db, active=False)
    patient = make_patient(db)
    assert can_access_patient(db, admin.user, _pid(patient)) is False


# --- 10. időhatárok az összerendelés-ellenőrzésben ---------------------------------


def test_assignment_boundaries(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    start = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    end = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    assign(db, doctor, patient, valid_from=start, valid_to=end)
    did = doctor.user.doctor_profile.id
    pid = _pid(patient)
    assert active_assignment_exists(db, did, pid, at=start - timedelta(microseconds=1)) is False
    assert active_assignment_exists(db, did, pid, at=start) is True  # valid_from <= at
    assert active_assignment_exists(db, did, pid, at=start + timedelta(days=5)) is True
    assert active_assignment_exists(db, did, pid, at=end - timedelta(microseconds=1)) is True
    assert active_assignment_exists(db, did, pid, at=end) is False  # valid_to > at kell
    assert active_assignment_exists(db, did, pid, at=end + timedelta(days=1)) is False


def test_open_ended_assignment_valid_far_in_future(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=datetime(2026, 1, 1, tzinfo=UTC))
    assert active_assignment_exists(
        db, doctor.user.doctor_profile.id, _pid(patient), at=datetime(2099, 1, 1, tzinfo=UTC)
    )


# --- 11. adatbázis-kényszer: egy aktív összerendelés páronként --------------------


def test_second_open_assignment_for_same_pair_rejected_by_db(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    db.commit()
    with pytest.raises(IntegrityError):
        assign(db, doctor, patient)
    db.rollback()


def test_open_assignment_allowed_after_closed_one(db: Session):
    """[MÓDOSÍTVA 2026-10-10] Kifejezett múltbeli valid_from, hogy a lezárás
    (valid_to = most) biztosan a kezdet után legyen (CHECK valid_to > valid_from)."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    first = assign(db, doctor, patient, valid_from=datetime.now(UTC) - timedelta(days=3))
    first.valid_to = datetime.now(UTC)
    db.flush()
    second = assign(db, doctor, patient)
    assert second.id != first.id
    assert second.valid_to is None
    assert can_access_patient(db, doctor.user, _pid(patient)) is True


def test_closing_default_valid_from_row_in_same_transaction_is_rejected(db: Session):
    """Az adatbázis now() a tranzakció kezdete; a szerveroldali alapértékkel
    felvett sor ugyanabban a tranzakcióban csak now()-nál későbbi valid_to-val
    zárható. Dokumentálja a jóváhagyott korlátot (lásd jelentés 5. pont)."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    link = DoctorPatient(
        doctor_id=doctor.user.doctor_profile.id, patient_id=patient.user.patient_profile.id
    )
    db.add(link)
    db.flush()
    db.refresh(link)
    db.commit()
    link.valid_to = link.valid_from  # = tranzakció-kezdet → üres időszak
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_overlapping_closed_intervals_rejected_by_db(db: Session):
    """EXCLUDE: két lezárt, de egymásba lógó időszak ugyanarra a párra tilos."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    now = datetime.now(UTC)
    assign(
        db, doctor, patient, valid_from=now - timedelta(days=30), valid_to=now - timedelta(days=10)
    )
    db.commit()
    with pytest.raises(IntegrityError):
        assign(
            db,
            doctor,
            patient,
            valid_from=now - timedelta(days=15),
            valid_to=now - timedelta(days=5),
        )
    db.rollback()


def test_interval_overlapping_open_ended_row_rejected_by_db(db: Session):
    """Nyitott sor mellé bármilyen, a kezdete utáni időszak tilos (az üres valid_to
    = végtelen)."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    now = datetime.now(UTC)
    assign(db, doctor, patient, valid_from=now - timedelta(days=10))
    db.commit()
    with pytest.raises(IntegrityError):
        assign(
            db,
            doctor,
            patient,
            valid_from=now + timedelta(days=100),
            valid_to=now + timedelta(days=200),
        )
    db.rollback()


def test_closed_interval_before_open_row_allowed(db: Session):
    """Történeti sor a nyitott sor KEZDETE ELŐTT nem fed át, felvehető."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    now = datetime.now(UTC)
    assign(db, doctor, patient, valid_from=now - timedelta(days=10))
    assign(
        db, doctor, patient, valid_from=now - timedelta(days=30), valid_to=now - timedelta(days=20)
    )


def test_adjacent_intervals_allowed(db: Session):
    """[valid_from, valid_to) félig nyílt: az egyik vége = a másik kezdete nem átfedés."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 2, 1, tzinfo=UTC)
    t2 = datetime(2026, 3, 1, tzinfo=UTC)
    assign(db, doctor, patient, valid_from=t0, valid_to=t1)
    assign(db, doctor, patient, valid_from=t1, valid_to=t2)
    assign(db, doctor, patient, valid_from=t2)  # nyitott folytatás
    did = doctor.user.doctor_profile.id
    pid = _pid(patient)
    assert active_assignment_exists(db, did, pid, at=t1 - timedelta(microseconds=1))
    assert active_assignment_exists(db, did, pid, at=t1)
    assert active_assignment_exists(db, did, pid, at=t2)
    assert not active_assignment_exists(db, did, pid, at=t0 - timedelta(microseconds=1))


def test_overlap_constraint_is_per_pair(db: Session):
    """Az EXCLUDE csak az azonos orvos–beteg párra vonatkozik."""
    doctor_a = make_doctor(db)
    doctor_b = make_doctor(db)
    p1 = make_patient(db)
    p2 = make_patient(db)
    now = datetime.now(UTC)
    assign(db, doctor_a, p1, valid_from=now - timedelta(days=5))
    assign(db, doctor_b, p1, valid_from=now - timedelta(days=5))  # másik orvos, ugyanaz a beteg
    assign(db, doctor_a, p2, valid_from=now - timedelta(days=5))  # ugyanaz az orvos, másik beteg


def test_multiple_closed_assignments_for_same_pair_allowed(db: Session):
    doctor = make_doctor(db)
    patient = make_patient(db)
    now = datetime.now(UTC)
    assign(
        db, doctor, patient, valid_from=now - timedelta(days=30), valid_to=now - timedelta(days=20)
    )
    assign(
        db, doctor, patient, valid_from=now - timedelta(days=10), valid_to=now - timedelta(days=1)
    )
    assign(db, doctor, patient)  # most egy aktív is


def test_open_assignments_for_different_pairs_allowed(db: Session):
    doctor_a = make_doctor(db)
    doctor_b = make_doctor(db)
    p1 = make_patient(db)
    p2 = make_patient(db)
    assign(db, doctor_a, p1)
    assign(db, doctor_a, p2)
    assign(db, doctor_b, p1)
    assign(db, doctor_b, p2)
    assert can_access_patient(db, doctor_a.user, _pid(p1))
    assert can_access_patient(db, doctor_b.user, _pid(p2))


def test_assignment_requires_existing_profiles(db: Session):
    """Idegen kulcsok: nem létező orvos- vagy betegprofilra nem vehető fel összerendelés."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    db.add(DoctorPatient(doctor_id=uuid.uuid4(), patient_id=patient.user.patient_profile.id))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    db.add(DoctorPatient(doctor_id=doctor.user.doctor_profile.id, patient_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_assignment_cannot_point_to_user_ids_instead_of_profile_ids(db: Session):
    """A User.id nem profil-azonosító; az idegen kulcs ezt elutasítja."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    db.add(DoctorPatient(doctor_id=doctor.user.id, patient_id=patient.user.id))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_db_rejects_two_simultaneously_valid_assignments_for_same_pair(db: Session):
    """[SPEC-VÁLTOZÁS 2026-10-10] Egy jövőbeli lejáratú és egy nyitott sor ugyanarra
    a párra most egyszerre érvényes lenne; az EXCLUDE-kényszer
    (ex_doctor_patients_no_overlap) ezt már elutasítja. Korábban lelet volt."""
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(
        db,
        doctor,
        patient,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_to=datetime.now(UTC) + timedelta(days=365),
    )
    db.commit()
    with pytest.raises(IntegrityError):
        assign(db, doctor, patient)
    db.rollback()
