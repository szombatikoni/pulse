"""Szabályok és riasztások (F11, F12, F17, F18; 03_adatmodell.md).

A Rule csak identitás (melyik betegre vonatkozik, ki hozta létre); a
paraméterek a RuleVersion-ben vannak, amely létrejötte után nem módosulhat
(az adatbázis is tiltja, lásd a migrációt). A riasztás és minden eseménye
tárolja az alkalmazott verziót és a kiváltó adatok azonosítóit: így utólag is
kiolvasható, melyik verzió, milyen adat alapján mit állapított meg.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum


class RuleType(StrEnum):
    """A négy paraméterezhető szabálytípus (F11). Az M2-ben az első működik."""

    THRESHOLD = "threshold"  # egyszeri küszöbátlépés
    WINDOW = "window"  # időablakos ismétlődés
    QUESTIONNAIRE = "questionnaire"  # kérdőív-pontszám: határ vagy romló trend
    MISSING_DATA = "missing_data"  # elmaradt adatküldés


class Severity(StrEnum):
    MODERATE = "moderate"  # közepes → Figyelem státusz
    SEVERE = "severe"  # súlyos → Súlyos státusz


class AlertStatus(StrEnum):
    """A riasztás életútja (4.3): keletkezett → megtekintett → felelőshöz
    rendelt → lezárt. Az M2-ben csak a keletkezés van; a többi az M3-ban."""

    NEW = "new"
    SEEN = "seen"
    ASSIGNED = "assigned"
    CLOSED = "closed"


class AlertEventType(StrEnum):
    CREATED = "created"
    SEEN = "seen"
    ASSIGNED = "assigned"
    CLOSED = "closed"
    RE_TRIGGERED = "re_triggered"  # nyitott riasztás mellett újabb kiváltó adat (F18)
    RULE_CHANGED = "rule_changed"
    TRIGGER_CORRECTED = "trigger_corrected"


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["RuleVersion"]] = relationship(
        back_populates="rule", order_by="RuleVersion.version_no"
    )


class RuleVersion(Base):
    """Egy szabály egy változata. Módosításkor új sor jön létre (version_no + 1),
    a régi változatlan marad (F12)."""

    __tablename__ = "rule_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.id"))
    version_no: Mapped[int] = mapped_column(SmallInteger)
    rule_type: Mapped[RuleType] = mapped_column(str_enum(RuleType, "rule_type", length=20))
    # A típusonkénti paraméterek (pl. küszöbök); a szerkezetüket a
    # services/rules.py ellenőrzi létrehozáskor.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity", length=16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    rule: Mapped[Rule] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("rule_id", "version_no"),)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    # Deduplikáció beteg + szabály szerint (F18): nyitott riasztásból
    # párosonként legfeljebb egy lehet (részleges egyedi index, lent).
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rules.id"))
    # A megnyitáskori verzió és kiváltó adatok; a későbbi eseményeké az
    # AlertEvent-ben van.
    rule_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_versions.id"))
    status: Mapped[AlertStatus] = mapped_column(
        str_enum(AlertStatus, "alert_status", length=16), default=AlertStatus.NEW
    )
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity", length=16))
    trigger_data_ids: Mapped[list[str]] = mapped_column(JSONB)
    # „Kiváltó adat javítva": az orvosnak kell felülvizsgálnia (F17, M3).
    needs_review: Mapped[bool] = mapped_column(default=False)
    # A kiértékelés idejét a szolgáltatás adja (a tesztekben szimulált idő).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rule_version: Mapped[RuleVersion] = relationship()
    events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="alert", order_by="AlertEvent.created_at"
    )

    __table_args__ = (
        Index(
            "uq_alerts_open_per_rule",
            "patient_id",
            "rule_id",
            unique=True,
            postgresql_where=text("status <> 'closed'"),
        ),
    )


class AlertEvent(Base):
    """A riasztás eseménytörténetének egy sora. Csak hozzáírni lehet; módosítani
    és törölni az adatbázis sem engedi (lásd a migrációt)."""

    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alerts.id"), index=True)
    # Ki váltotta ki; NULL = a rendszer (pl. kiértékelés).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[AlertEventType] = mapped_column(
        str_enum(AlertEventType, "alert_event_type", length=20)
    )
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rule_versions.id"))
    trigger_data_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    # Lezárásnál kötelező indoklás (M3).
    reason: Mapped[str | None] = mapped_column(Text)
    # A kiértékelés idejét a szolgáltatás adja (a tesztekben szimulált idő).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    alert: Mapped[Alert] = relationship(back_populates="events")
