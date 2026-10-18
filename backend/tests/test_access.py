"""Hozzáférés a betegadatokhoz (F2, F3) — a szolgáltatásréteg szintjén.
A végpontszintű jogosultsági tesztek a betegadatot adó végpontokkal jönnek."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.deps import require_roles
from app.models import UserRole
from app.services.access import can_access_patient
from tests.factories import assign, make_admin, make_doctor, make_patient


def patient_id(user):
    return user.patient_profile.id


def test_patient_sees_only_own_data(db):
    me = make_patient(db, email="en@test.example")
    other = make_patient(db, email="mas@test.example")
    assert can_access_patient(db, me, patient_id(me))
    assert not can_access_patient(db, me, patient_id(other))


def test_doctor_sees_only_assigned_patients(db):
    doctor = make_doctor(db)
    mine = make_patient(db, email="sajat@test.example")
    foreign = make_patient(db, email="idegen@test.example")
    assign(db, doctor, mine)
    assert can_access_patient(db, doctor, patient_id(mine))
    assert not can_access_patient(db, doctor, patient_id(foreign))


def test_ending_assignment_revokes_access_immediately(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    link = assign(db, doctor, patient, valid_from=datetime.now(UTC) - timedelta(days=30))
    assert can_access_patient(db, doctor, patient_id(patient))
    link.valid_to = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert not can_access_patient(db, doctor, patient_id(patient))


def test_new_assignment_grants_access_immediately(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assert not can_access_patient(db, doctor, patient_id(patient))
    assign(db, doctor, patient)
    assert can_access_patient(db, doctor, patient_id(patient))


def test_future_assignment_does_not_grant_access_yet(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient, valid_from=datetime.now(UTC) + timedelta(days=1))
    assert not can_access_patient(db, doctor, patient_id(patient))


def test_admin_has_no_access_to_patient_data(db):
    admin = make_admin(db)
    patient = make_patient(db)
    assert not can_access_patient(db, admin, patient_id(patient))


def test_inactive_doctor_loses_access(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    doctor.is_active = False
    assert not can_access_patient(db, doctor, patient_id(patient))


def test_only_one_active_assignment_per_pair(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient)
    with pytest.raises(IntegrityError):
        assign(db, doctor, patient)


def test_ended_assignment_can_be_followed_by_a_new_one(db):
    # A lezárt összerendelés történetként megmarad, mellette újra lehet rendelni.
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(
        db,
        doctor,
        patient,
        valid_from=datetime.now(UTC) - timedelta(days=30),
        valid_to=datetime.now(UTC) - timedelta(days=1),
    )
    assign(db, doctor, patient)
    assert can_access_patient(db, doctor, patient_id(patient))


def test_require_roles_allows_and_forbids(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    only_doctors = require_roles(UserRole.DOCTOR)
    assert only_doctors(doctor) is doctor
    with pytest.raises(HTTPException) as error:
        only_doctors(patient)
    assert error.value.status_code == 403


def test_overlapping_assignments_for_same_pair_are_rejected(db):
    # Egy jövőben lejáró és egy nyitott összerendelés most mindkettő érvényes
    # lenne: az átfedést az adatbázis kizárja (független teszt lelete).
    doctor = make_doctor(db)
    patient = make_patient(db)
    assign(db, doctor, patient, valid_to=datetime.now(UTC) + timedelta(days=365))
    with pytest.raises(IntegrityError):
        assign(db, doctor, patient)


def test_same_patient_can_have_assignments_with_different_doctors(db):
    # Az átfedés-tilalom csak ugyanarra az orvos–beteg párra vonatkozik.
    first = make_doctor(db, email="o1@test.example")
    second = make_doctor(db, email="o2@test.example")
    patient = make_patient(db)
    assign(db, first, patient)
    assign(db, second, patient)
    assert can_access_patient(db, first, patient_id(patient))
    assert can_access_patient(db, second, patient_id(patient))


def test_assignment_cannot_end_before_it_starts(db):
    doctor = make_doctor(db)
    patient = make_patient(db)
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError):
        assign(db, doctor, patient, valid_from=now, valid_to=now - timedelta(days=1))
