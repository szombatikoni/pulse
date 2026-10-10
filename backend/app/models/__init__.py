"""SQLAlchemy-modellek. Az Alembic a Base.metadata alapján generál migrációt,
ezért minden új modellt itt is importálni kell."""

from app.models.base import Base
from app.models.user import DoctorPatient, DoctorProfile, PatientProfile, User, UserRole

__all__ = ["Base", "DoctorPatient", "DoctorProfile", "PatientProfile", "User", "UserRole"]
