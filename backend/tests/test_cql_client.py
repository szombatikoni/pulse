"""A CQL-szolgáltatás kliensének hibaágai (M3, K2) egy helyi HTTP-szerverrel:
siker, nem 200-as válasz (413 és más 4xx megkülönböztetve), nem JSON, nem
objektum, időtúllépés (a teljes hívásra, lassan csöpögtető válasznál is), túl
nagy válasz, elérhetetlen cím, megszakadt kapcsolat, és hogy a környezeti
proxybeállítás nem számít. Mindegyik hiba ugyanaz a kivétel (CqlServiceError)."""

import json
import socket
import threading
import time
import urllib.parse
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services.cql_client import CqlServiceError, evaluate


class Handler(BaseHTTPRequestHandler):
    """A válasz a kérés útvonalától függ (a teszt a base url-lel választ)."""

    received: list[dict] = []

    def log_message(self, *args) -> None:  # a tesztkimenet maradjon tiszta
        pass

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:  # a kliens a válasz közben bontott (pl. túl nagy válasz)
            pass

    def _drip(self, body: bytes, pause: float) -> None:
        """A fejléc azonnal, a törzs bájtonként, `pause` szünetekkel."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            for byte in body:
                self.wfile.write(bytes([byte]))
                self.wfile.flush()
                time.sleep(pause)
        except OSError:  # a kliens az időkorlát után bontott
            pass

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        Handler.received.append({"path": self.path, "payload": payload})
        mode = self.path.split("/")[1]
        if mode == "ok":
            self._send(200, json.dumps({"result": {"targetMet": None}, "durationMs": 1}).encode())
        elif mode == "error":
            self._send(500, b'{"error": "evaluation_failed", "message": "x"}')
        elif mode == "accepted":
            self._send(202, b"{}")
        elif mode == "text":
            self._send(200, b"nem json")
        elif mode == "list":
            self._send(200, b"[1, 2]")
        elif mode == "slow":
            time.sleep(1)
            self._send(200, b"{}")
        elif mode == "too-large-request":
            self._send(413, b'{"error": "payload_too_large", "message": "x"}')
        elif mode == "bad-request":
            self._send(400, b'{"error": "invalid_bundle", "message": "x"}')
        elif mode == "drip":
            # Minden darab gyorsan jön (0,2 s), de együtt kb. 7 s: csak a teljes
            # hívásra vonatkozó időkorlát állítja meg.
            self._drip(b'{"result": {}, "padding": "0123456"}', 0.2)
        elif mode == "huge":
            self._send(200, b'{"x": "' + b"a" * (1024 * 1024) + b'"}')
        elif mode == "drop":
            # Fejléc nélkül zárja a kapcsolatot.
            self.connection.shutdown(socket.SHUT_RDWR)


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_success_posts_json_and_returns_the_object(server):
    Handler.received.clear()
    answer = evaluate({"bundle": {"resourceType": "Bundle"}}, url=f"{server}/ok/", timeout=2)
    assert answer == {"result": {"targetMet": None}, "durationMs": 1}
    assert Handler.received == [
        {"path": "/ok/evaluate", "payload": {"bundle": {"resourceType": "Bundle"}}}
    ]


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("error", "http_500"),
        ("accepted", "http_202"),
        ("too-large-request", "http_413"),
        ("bad-request", "http_400"),
        ("huge", "response_too_large"),
        ("text", "invalid_response"),
        ("list", "invalid_response"),
        ("slow", "timeout"),
        ("drop", "unreachable"),
    ],
)
def test_failures_are_one_exception(server, mode, reason):
    with pytest.raises(CqlServiceError) as error:
        evaluate({}, url=f"{server}/{mode}", timeout=0.3)
    assert error.value.reason == reason


def test_unreachable_address():
    # Egy szabad port, amelyen senki nem figyel. (Windowson az elutasított
    # kapcsolat kb. 2 s után derül ki, ezért a bőséges időkorlát.)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(CqlServiceError) as error:
        evaluate({}, url=f"http://127.0.0.1:{port}", timeout=10)
    assert error.value.reason == "unreachable"


def test_service_error_code_is_in_the_message(server):
    """A 413-at és a többi 4xx-et a reason különbözteti meg, a szolgáltatás
    saját hibakódja az üzenetben van."""
    with pytest.raises(CqlServiceError) as error:
        evaluate({}, url=f"{server}/too-large-request", timeout=2)
    assert error.value.reason == "http_413"
    assert "payload_too_large" in str(error.value)


def test_timeout_is_for_the_whole_call(server):
    """Lassan csöpögtető válasz: minden bájt 0,2 s-on belül jön (a socket-
    műveletenkénti időkorlát sosem járna le), de a teljes hívás 0,6 s után
    megszakad, nem a válasz végén (kb. 7 s)."""
    started = time.monotonic()
    with pytest.raises(CqlServiceError) as error:
        evaluate({}, url=f"{server}/drip", timeout=0.6)
    elapsed = time.monotonic() - started
    assert error.value.reason == "timeout"
    assert elapsed < 1.5


def test_environment_proxy_is_not_used(server, monkeypatch):
    """A proxybeállítás egy nem létező proxyra mutat; a hívás mégis közvetlenül
    megy, és sikerül."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, f"http://127.0.0.1:{port}")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    answer = evaluate({}, url=f"{server}/ok", timeout=2)
    assert answer["durationMs"] == 1


def test_unsupported_address_is_unreachable():
    with pytest.raises(CqlServiceError) as error:
        evaluate({}, url="https://cql:8080", timeout=1)
    assert error.value.reason == "unreachable"


def test_connect_timeout_is_reported_as_timeout(monkeypatch):
    """A kapcsolódás közbeni időtúllépés is timeout."""
    import http.client

    def connect(self):
        raise TimeoutError("timed out")

    monkeypatch.setattr(http.client.HTTPConnection, "connect", connect)
    with pytest.raises(CqlServiceError) as error:
        evaluate({}, url="http://cql:8080")
    assert error.value.reason == "timeout"


def test_defaults_come_from_the_settings(monkeypatch):
    import http.client

    from app.core.config import settings

    seen = {}

    def connect(self):
        seen.update(host=self.host, port=self.port, timeout=self.timeout)
        raise ConnectionRefusedError

    monkeypatch.setattr(http.client.HTTPConnection, "connect", connect)
    with pytest.raises(CqlServiceError) as error:
        evaluate({})
    assert error.value.reason == "unreachable"
    target = urllib.parse.urlsplit(settings.cql_service_url)
    assert (seen["host"], seen["port"]) == (target.hostname, target.port or 80)
    assert 0 < seen["timeout"] <= settings.cql_timeout_seconds
