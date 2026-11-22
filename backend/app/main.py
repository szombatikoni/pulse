import json

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

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


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> Response:
    """A FastAPI szokásos 422-es válasza. Egyetlen kivétel: ha a hibás bemenetben
    magányos surrogate van (pl. "\\ud800"), a hibalista UTF-8-ba írása elbukna
    (500), ezért ilyenkor a válasz ASCII-escape-elt JSON, ugyanazzal a tartalommal."""
    try:
        return await request_validation_exception_handler(request, exc)
    except UnicodeEncodeError:
        body = json.dumps({"detail": jsonable_encoder(exc.errors())})
        return Response(body, status_code=422, media_type="application/json")
