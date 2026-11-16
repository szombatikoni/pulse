"""Vékony HTTP-kliens a CQL-szolgáltatáshoz (M3, K2; integration/szolgaltatas.mjs).

A standard könyvtárral (http.client), új függőség nélkül (a hallgató döntése,
D6a). Minden hiba egyetlen kivétel (CqlServiceError): hibás cím, időtúllépés,
kapcsolódási hiba, nem 200-as válasz, túl nagy vagy nem értelmezhető törzs.
Automatikus újrapróbálás nincs (D7a): a gomb újra megnyomható.

Az időkorlát egy, a kezdéskor kiszámolt határidő, de nem minden lépésre
egyformán hat. A törzs olvasására a teljes határidő érvényes: minden darab
előtt a maradék idő lesz a socket időkorlátja, így egy lassan csöpögtető
szolgáltatás sem tarthatja fel tovább. A kapcsolódásra (és a kérés küldésére),
valamint a válasz fejlécének olvasására csak műveletenként érvényes a maradék
idő (a kezdéskori, illetve a küldés utáni): ott egy-egy socket-művelet ennyit
várhat, több művelet együtt túllépheti. A névfeloldásra (getaddrinfo) a
határidő nem hat. Mindkettő ismert korlát. A választ darabonként,
legfeljebb MAX_RESPONSE_BYTES-ig olvassuk.

A http.client a környezeti proxybeállítást (HTTP_PROXY stb.) nem nézi, ezért a
belső hívás akkor sem megy proxyn át, ha a gépen van ilyen beállítás. (Az
urllib.request ezt alapból követné; ezért nem azt használjuk.)

A tesztek a végpont függőségén át cserélik ki (api/nice.py, get_cql_evaluate),
a kliens hibaágait pedig egy helyi HTTP-szerverrel próbálják ki.
"""

import http.client
import json
import socket
import time
import urllib.parse
from typing import Any

from app.core.config import settings

# A válasz felső korlátja (egy kiértékelés eredménye néhány kilobájt).
MAX_RESPONSE_BYTES = 1024 * 1024
_CHUNK = 64 * 1024


class CqlServiceError(Exception):
    """A CQL-szolgáltatás nem adott használható választ. A `reason` rövid
    gépi ok a naplóhoz és a tesztekhez: timeout, unreachable, invalid_url
    (hibás CQL_SERVICE_URL), http_<kód> (pl. http_413 túl nagy kérés, http_400
    hibás kérés, http_500 hiba a kiértékelésben), response_too_large,
    invalid_response. A végpont mindegyikre ugyanazt adja (503,
    cql_unavailable)."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason


class _Deadline:
    """A teljes hívás határideje; remaining() a hátralévő másodperc, és
    időtúllépést jelez, ha már nincs."""

    def __init__(self, seconds: float) -> None:
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        left = self.end - time.monotonic()
        if left <= 0:
            raise CqlServiceError("timeout", "a teljes hívás időkorlátja lejárt")
        return left


def _read_body(
    response: http.client.HTTPResponse, sock: socket.socket, deadline: _Deadline
) -> bytes:
    """A törzs darabonként, minden darab előtt a maradék idővel mint socket-
    időkorláttal; MAX_RESPONSE_BYTES fölött hiba."""
    parts: list[bytes] = []
    size = 0
    # A válasz magától lezárul, ha a teljes törzs megjött (Content-Length).
    while not response.isclosed():
        sock.settimeout(deadline.remaining())
        part = response.read1(_CHUNK)
        if not part:
            break
        size += len(part)
        if size > MAX_RESPONSE_BYTES:
            raise CqlServiceError("response_too_large", f"több mint {MAX_RESPONSE_BYTES} bájt")
        parts.append(part)
    return b"".join(parts)


def evaluate(
    payload: dict[str, Any], *, url: str | None = None, timeout: float | None = None
) -> dict[str, Any]:
    """POST /evaluate a szolgáltatásnak; a válasz JSON-objektuma (library,
    engine, evaluationTime, result, durationMs). A cím és az időkorlát
    alapból a beállításokból jön."""
    deadline = _Deadline(timeout or settings.cql_timeout_seconds)
    address = url or settings.cql_service_url
    try:
        # Hibás cím (pl. http://[::1, http://localhost:abc, 99999-es port,
        # szóköz a gépnévben): ValueError vagy InvalidURL, már itt.
        target = urllib.parse.urlsplit(address)
        if target.scheme != "http" or not target.hostname:
            raise CqlServiceError("unreachable", f"nem támogatott cím: {target.geturl()}")
        connection = http.client.HTTPConnection(
            target.hostname, target.port or 80, timeout=deadline.remaining()
        )
    except (ValueError, http.client.InvalidURL) as error:
        raise CqlServiceError("invalid_url", str(error)) from error
    path = f"{target.path.rstrip('/')}/evaluate"
    body = json.dumps(payload).encode("utf-8")

    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        sock = connection.sock
        assert sock is not None  # a request() után a kapcsolat él
        sock.settimeout(deadline.remaining())
        response = connection.getresponse()
        status = response.status
        data = _read_body(response, sock, deadline)
    except TimeoutError as error:
        raise CqlServiceError("timeout") from error
    except UnicodeError as error:
        # A gépnév IDNA-kódolása a névfeloldáskor bukik el (pl. http://a..b:80,
        # 63 karakternél hosszabb címke): ez is hibás cím.
        raise CqlServiceError("invalid_url", str(error)) from error
    except (OSError, http.client.HTTPException) as error:
        # Elutasított kapcsolat, névfeloldási hiba, megszakadt válasz ...
        raise CqlServiceError("unreachable", str(error)) from error
    finally:
        connection.close()
    if status != 200:
        # A szolgáltatás válaszolt, de hibával; a saját hibakódja (pl.
        # payload_too_large) az üzenetbe kerül, ha kiolvasható.
        raise CqlServiceError(f"http_{status}", _error_code(data))
    try:
        parsed = json.loads(data)
    except ValueError as error:
        raise CqlServiceError("invalid_response", "a törzs nem JSON") from error
    if not isinstance(parsed, dict):
        raise CqlServiceError("invalid_response", "a törzs nem JSON-objektum")
    return parsed


def _error_code(data: bytes) -> str:
    """A szolgáltatás {error, message} válaszának error mezője, ha van."""
    try:
        code = json.loads(data).get("error")
    except (ValueError, AttributeError):
        return ""
    return code if isinstance(code, str) else ""
