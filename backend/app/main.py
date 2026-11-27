import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

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


def errors_without_input(exc: RequestValidationError) -> list[dict[str, Any]]:
    """A hibalista a beküldött érték (input) nélkül. Az input a hibás mező
    értékét, hiányzó mezőnél vagy rossz típusú törzsnél pedig a teljes beküldött
    objektumot küldené vissza, benne a jelszóval (belépés, új felhasználó). A
    frontend és a tesztek csak a loc, msg és type mezőt olvassák (az OpenAPI
    422-es sémájában ezek kötelezők, az input és a ctx opcionális), ezért az
    input minden hibából kimarad, nem csak a titkos mezőkéből."""
    return [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> Response:
    """A FastAPI szokásos 422-es válasza, a beküldött értékek nélkül (lásd
    errors_without_input). Ha a hibaüzenetben magányos surrogate van (pl.
    "\\ud800"), a hibalista UTF-8-ba írása elbukna (500), ezért ilyenkor a válasz
    ASCII-escape-elt JSON, ugyanazzal a tartalommal."""
    detail = jsonable_encoder(errors_without_input(exc))
    try:
        return JSONResponse({"detail": detail}, status_code=422)
    except UnicodeEncodeError:
        body = json.dumps({"detail": detail})
        return Response(body, status_code=422, media_type="application/json")
