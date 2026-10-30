from fastapi import APIRouter

from app.api import admin, auth, fhir, health, measurements, patients, questionnaires, tasks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(measurements.router)
api_router.include_router(patients.router)
api_router.include_router(questionnaires.router)
api_router.include_router(tasks.router)
api_router.include_router(fhir.router)
