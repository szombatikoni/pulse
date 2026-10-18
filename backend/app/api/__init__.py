from fastapi import APIRouter

from app.api import auth, health, measurements, patients, questionnaires, tasks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(measurements.router)
api_router.include_router(patients.router)
api_router.include_router(questionnaires.router)
api_router.include_router(tasks.router)
