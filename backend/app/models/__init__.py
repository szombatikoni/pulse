"""SQLAlchemy-modellek. Az Alembic a Base.metadata alapján generál migrációt,
ezért minden új modellt itt is importálni kell."""

from app.models.alert import (
    Alert,
    AlertEvent,
    AlertEventType,
    AlertStatus,
    Rule,
    RuleType,
    RuleVersion,
    Severity,
)
from app.models.base import Base
from app.models.measurement import (
    Measurement,
    MeasurementComponent,
    MeasurementType,
    MeasurementValue,
)
from app.models.questionnaire import (
    Answer,
    Assignment,
    AssignmentTarget,
    Frequency,
    GoodEnd,
    Question,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    QuestionType,
    Submission,
)
from app.models.user import DoctorPatient, DoctorProfile, PatientProfile, User, UserRole

__all__ = [
    "Alert",
    "AlertEvent",
    "AlertEventType",
    "AlertStatus",
    "Answer",
    "Assignment",
    "AssignmentTarget",
    "Base",
    "DoctorPatient",
    "DoctorProfile",
    "Frequency",
    "GoodEnd",
    "Measurement",
    "MeasurementComponent",
    "MeasurementType",
    "MeasurementValue",
    "PatientProfile",
    "Question",
    "QuestionType",
    "QuestionnaireTemplate",
    "QuestionnaireVersion",
    "Rule",
    "RuleType",
    "RuleVersion",
    "Severity",
    "Submission",
    "User",
    "UserRole",
]
