"""Kérdőívek (F6, F13) és kirendelésük (F14); 03_adatmodell.md.

A QuestionnaireTemplate csak identitás; a tartalom (kérdések, pontozás,
kiértékelési sávok) a QuestionnaireVersion-ben és a Question-ben van, amelyek
létrejöttük után nem módosulhatnak (az adatbázis is tiltja). Minden kitöltés
a kitöltéskori verzióra hivatkozik, így a régi kitöltések jelentése és
pontszáma utólag nem változik.

Az M2-ben az alkalmak (AssignmentOccurrence) még nincsenek: a beteg a neki
kirendelt kérdőív aktuális verzióját tölti ki. Az alkalmak, a határidők és a
háttérfolyamat az M3-ban jönnek.
"""

import uuid
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum


class QuestionType(StrEnum):
    SCALE = "scale"  # skála, pl. 1–5
    SINGLE = "single"  # egy válasz a felsoroltakból
    MULTI = "multi"  # több válasz a felsoroltakból


class GoodEnd(StrEnum):
    """Skálás kérdésnél melyik vég jelenti a jobb állapotot (F13)."""

    MIN = "min"
    MAX = "max"


class AssignmentTarget(StrEnum):
    QUESTIONNAIRE = "questionnaire"
    MEASUREMENT = "measurement"


class Frequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    EVERY_N_DAYS = "every_n_days"


class QuestionnaireTemplate(Base):
    __tablename__ = "questionnaire_templates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Programon belüli, beszédes azonosító (pl. "wellbeing").
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(default=True)

    versions: Mapped[list["QuestionnaireVersion"]] = relationship(
        back_populates="template", order_by="QuestionnaireVersion.version_no"
    )


class QuestionnaireVersion(Base):
    """A kérdőív egy változata a kérdéseivel és a kiértékelési sávokkal."""

    __tablename__ = "questionnaire_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questionnaire_templates.id"))
    version_no: Mapped[int] = mapped_column(SmallInteger)
    # Kiértékelési sávok az összpontszámra, pl.
    # [{"band": "normal", "min": 0, "max": 5}, {"band": "warning", "min": 6, "max": 10}, ...]
    # A sávok a verzió részei: új verzió a saját pontozásával a saját sávjait hozza.
    scoring_thresholds: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    template: Mapped[QuestionnaireTemplate] = relationship(back_populates="versions")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="version", order_by="Question.order_no"
    )

    __table_args__ = (UniqueConstraint("template_id", "version_no"),)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questionnaire_versions.id"))
    order_no: Mapped[int] = mapped_column(SmallInteger)
    question_type: Mapped[QuestionType] = mapped_column(
        str_enum(QuestionType, "question_type", length=16)
    )
    text: Mapped[str] = mapped_column(Text)
    scale_min: Mapped[int | None] = mapped_column(SmallInteger)
    scale_max: Mapped[int | None] = mapped_column(SmallInteger)
    good_end: Mapped[GoodEnd | None] = mapped_column(str_enum(GoodEnd, "good_end", length=8))
    # A válasz → pont tábla, a verzióval együtt rögzítve: kitöltéskor a pont
    # innen olvasódik ki, így kódmódosítás sem írja át a régi pontokat.
    # [{"value": "4", "label": "4", "score": 1}, ...]
    options_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)

    version: Mapped[QuestionnaireVersion] = relationship(back_populates="questions")

    __table_args__ = (
        UniqueConstraint("version_id", "order_no"),
        # Skálás kérdésnél kötelező a skála két vége és a „jobb vég" (F13).
        CheckConstraint(
            "question_type <> 'scale' OR (scale_min IS NOT NULL AND scale_max IS NOT NULL"
            " AND scale_min < scale_max AND good_end IS NOT NULL)",
            name="scale_fields",
        ),
    )


class Assignment(Base):
    """Az orvos előírása (követési terv eleme, F14): mit, milyen gyakran,
    mettől meddig. Az M2-ben csak a kérdőív kirendelése használja; az alkalmak
    és a határidők az M3-ban jönnek."""

    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    target_kind: Mapped[AssignmentTarget] = mapped_column(
        str_enum(AssignmentTarget, "assignment_target", length=16)
    )
    questionnaire_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("questionnaire_templates.id")
    )
    measurement_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("measurement_types.id")
    )
    frequency: Mapped[Frequency] = mapped_column(str_enum(Frequency, "frequency", length=16))
    interval_days: Mapped[int | None] = mapped_column(SmallInteger)
    suggested_time: Mapped[time | None] = mapped_column(Time)
    due_time: Mapped[time] = mapped_column(Time)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[QuestionnaireTemplate | None] = relationship()

    __table_args__ = (
        # Pontosan az egyik cél van kitöltve, a target_kind szerint.
        CheckConstraint(
            "(target_kind = 'questionnaire' AND questionnaire_template_id IS NOT NULL"
            " AND measurement_type_id IS NULL) OR (target_kind = 'measurement'"
            " AND measurement_type_id IS NOT NULL AND questionnaire_template_id IS NULL)",
            name="one_target",
        ),
        CheckConstraint(
            "frequency <> 'every_n_days' OR interval_days > 0", name="interval_for_every_n_days"
        ),
    )


class Submission(Base):
    """Egy kérdőív-kitöltés. A verzió a kitöltéskori; a pontszám egész (a
    klinikai kérdőívek konvenciója, 03_adatmodell.md)."""

    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questionnaire_versions.id"))
    total_score: Mapped[int] = mapped_column(SmallInteger)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    version: Mapped[QuestionnaireVersion] = relationship()
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"))
    # A válasz: skálánál és egyválasztósnál egy érték, többválasztósnál lista.
    value: Mapped[Any] = mapped_column(JSONB)
    score: Mapped[int] = mapped_column(SmallInteger)

    submission: Mapped[Submission] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship()

    __table_args__ = (UniqueConstraint("submission_id", "question_id"),)
