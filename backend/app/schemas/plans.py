import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.models import AssignmentTarget, Frequency, RuleType
from app.models.questionnaire import REVOKE_NOTE_MAX
from app.services.notifications import AlertFeedback
from app.services.plans import PlanEntry, PlanNotice, PlanParams

# Az orvos indoklása a betegnek (visszavonásnál és módosításnál, nem kötelező).
Note = Field(
    default=None,
    max_length=REVOKE_NOTE_MAX,
    description="Indoklás a betegnek (nem kötelező); a beteg is látja.",
    examples=["A vérnyomása stabil, elég hetente mérni."],
)


class PlanParamsIn(BaseModel):
    """Az előírás paraméterei; a modell ellenőrzéseivel összhangban (N naponta
    csak pozitív időközzel, napi és heti előírásnál időköz nélkül)."""

    frequency: Frequency
    interval_days: int | None = Field(default=None, ge=1, le=365)
    due_time: time = Field(examples=["10:00"])
    suggested_time: time | None = Field(default=None, examples=["07:30"])
    # Üresen új előírásnál a mai nap. Múltbeli kezdet nem adható meg.
    # Módosításnál nem választható: mindig a mai nap (a még el nem kezdett
    # régi előírásnál a régi kezdete); ettől eltérő érték: start_fixed hiba.
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def check_interval(self) -> "PlanParamsIn":
        if self.frequency is Frequency.EVERY_N_DAYS and self.interval_days is None:
            raise ValueError("N napos előírásnál kötelező az időköz (interval_days)")
        if self.frequency is not Frequency.EVERY_N_DAYS and self.interval_days is not None:
            raise ValueError("időköz (interval_days) csak N napos előírásnál adható meg")
        return self

    def params(self) -> PlanParams:
        return PlanParams(
            frequency=self.frequency,
            interval_days=self.interval_days,
            due_time=self.due_time,
            suggested_time=self.suggested_time,
            start_date=self.start_date,
            end_date=self.end_date,
        )


class AssignmentCreate(PlanParamsIn):
    kind: AssignmentTarget
    # A méréstípus vagy a kérdőív kódja, a kind szerint.
    code: str = Field(min_length=1, max_length=50, examples=["blood_pressure"])


class AssignmentReplace(PlanParamsIn):
    """Módosítás: a cél a régi előírásé, csak a paraméterek újak. Az indoklás a
    régi előíráshoz kerül."""

    note: str | None = Note


class AssignmentRevoke(BaseModel):
    note: str | None = Note


class AssignmentOut(BaseModel):
    id: uuid.UUID
    kind: AssignmentTarget
    code: str
    name: str
    frequency: Frequency
    interval_days: int | None
    due_time: time
    suggested_time: time | None
    start_date: date
    end_date: date | None
    revoked_at: datetime | None
    assigned_by: str = Field(description="Az előíró orvos neve.")
    status: Literal["active", "upcoming", "ended", "revoked"]
    revoke_note: str | None = Field(description="Az orvos indoklása (visszavonás, módosítás).")
    # Módosításnál az az előírás, amely ennek a helyébe lépett (az adatból
    # kiolvasva: ugyanaz a cél, és a kezdete ott van, ahol ez véget ért).
    replaced_by: uuid.UUID | None


def assignment_out(entry: PlanEntry) -> AssignmentOut:
    a = entry.assignment
    return AssignmentOut(
        id=a.id,
        kind=a.target_kind,
        code=entry.code,
        name=entry.name,
        frequency=a.frequency,
        interval_days=a.interval_days,
        due_time=a.due_time,
        suggested_time=a.suggested_time,
        start_date=a.start_date,
        end_date=a.end_date,
        revoked_at=a.revoked_at,
        assigned_by=entry.assigned_by,
        status=entry.status,
        revoke_note=a.revoke_note,
        replaced_by=entry.replaced_by,
    )


class PlanNoticeOut(BaseModel):
    """Jelzés a betegnek: egy előírását a közelmúltban visszavonták vagy
    módosították. Módosításnál az érvényes előírás paramétereivel."""

    kind: Literal["revoked", "modified"]
    changed_at: datetime
    note: str | None
    target_kind: AssignmentTarget
    code: str
    name: str
    # A lezárt (régi) előírás gyakorisága, a jelzés szövegéhez.
    frequency: Frequency
    interval_days: int | None
    # Csak módosításnál: az új előírás.
    new_frequency: Frequency | None
    new_interval_days: int | None
    new_due_time: time | None
    new_start_date: date | None


class AlertFeedbackNoticeOut(BaseModel):
    """Jelzés a betegnek: az orvos visszajelzése egy riasztás lezárásakor (M3,
    A6). Egyirányú, válaszolni nem lehet. A changed_at a létrehozás ideje (a
    közös rendezéshez ugyanaz a mezőnév, mint az előírás-jelzéseknél)."""

    kind: Literal["alert_feedback"]
    changed_at: datetime
    text: str
    doctor_name: str
    alert_id: uuid.UUID
    # Miről szólt a riasztás: a szabály típusa és célpontja (méréstípus vagy
    # kérdőív kódja és neve), pl. „a vérnyomás-riasztás lezárásakor".
    rule_type: RuleType
    target_code: str
    target_name: str


def alert_feedback_out(feedback: AlertFeedback) -> AlertFeedbackNoticeOut:
    n = feedback.notification
    assert n.alert_id is not None
    return AlertFeedbackNoticeOut(
        kind="alert_feedback",
        changed_at=n.created_at,
        text=n.text,
        doctor_name=feedback.doctor_name,
        alert_id=n.alert_id,
        rule_type=feedback.rule_type,
        target_code=feedback.target_code,
        target_name=feedback.target_name,
    )


# A betegoldali jelzések egy listában, a kind szerint megkülönböztetve.
NoticeOut = Annotated[PlanNoticeOut | AlertFeedbackNoticeOut, Field(discriminator="kind")]


def plan_notice_out(notice: PlanNotice) -> PlanNoticeOut:
    old, new = notice.entry.assignment, notice.current.assignment if notice.current else None
    return PlanNoticeOut(
        kind=notice.kind,
        changed_at=notice.changed_at,
        note=notice.note,
        target_kind=old.target_kind,
        code=notice.entry.code,
        name=notice.entry.name,
        frequency=old.frequency,
        interval_days=old.interval_days,
        new_frequency=new.frequency if new else None,
        new_interval_days=new.interval_days if new else None,
        new_due_time=new.due_time if new else None,
        new_start_date=new.start_date if new else None,
    )
