"""Vékony HTTP-kliens a CQL-szolgáltatáshoz (M3, K2; integration/szolgaltatas.mjs).

A standard könyvtárral (urllib.request), új függőség nélkül (a hallgató döntése,
D6a). Minden hiba egyetlen kivétel (CqlServiceError): időtúllépés, kapcsolódási
hiba, nem 200-as válasz, nem értelmezhető törzs. Automatikus újrapróbálás nincs
(D7a): a gomb újra megnyomható.

A tesztek a végpont függőségén át cserélik ki (api/nice.py, get_cql_evaluate),
a kliens hibaágait pedig egy helyi HTTP-szerverrel próbálják ki.
"""

import http.client
import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings


class CqlServiceError(Exception):
    """A CQL-szolgáltatás nem adott használható választ. A `reason` rövid
    gépi ok (timeout, unreachable, http_<kód>, invalid_response) a naplóhoz és
    a tesztekhez; a végpont mindegyikre ugyanazt adja (503, cql_unavailable)."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(f"{reason}: {message}" if message else reason)
        self.reason = reason


def evaluate(
    payload: dict[str, Any], *, url: str | None = None, timeout: float | None = None
) -> dict[str, Any]:
    """POST /evaluate a szolgáltatásnak; a válasz JSON-objektuma (library,
    engine, evaluationTime, result, durationMs). A cím és az időtúllépés
    alapból a beállításokból jön."""
    base = (url or settings.cql_service_url).rstrip("/")
    request = urllib.request.Request(
        f"{base}/evaluate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout or settings.cql_timeout_seconds
        ) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as error:
        # A szolgáltatás válaszolt, de hibával (400, 500 ...).
        raise CqlServiceError(f"http_{error.code}") from error
    except TimeoutError as error:
        raise CqlServiceError("timeout") from error
    except urllib.error.URLError as error:
        # A kapcsolódási időtúllépést is ez csomagolja (reason: TimeoutError).
        reason = "timeout" if isinstance(error.reason, TimeoutError) else "unreachable"
        raise CqlServiceError(reason, str(error.reason)) from error
    except (OSError, http.client.HTTPException) as error:
        # Pl. a kapcsolat megszakadt a válasz közben.
        raise CqlServiceError("unreachable", str(error)) from error
    if status != 200:
        raise CqlServiceError(f"http_{status}")
    try:
        parsed = json.loads(body)
    except ValueError as error:
        raise CqlServiceError("invalid_response", "a törzs nem JSON") from error
    if not isinstance(parsed, dict):
        raise CqlServiceError("invalid_response", "a törzs nem JSON-objektum")
    return parsed
