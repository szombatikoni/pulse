from fastapi import FastAPI

from app.api import api_router

# Minden végpont az /api előtag alatt van: élesben az nginx ezt az útvonalat
# továbbítja a backendnek, fejlesztéskor a Vite dev szerver ugyanígy.
app = FastAPI(
    title="PULSE API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(api_router, prefix="/api")
