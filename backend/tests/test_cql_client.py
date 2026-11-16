"""A CQL-szolgáltatás kliensének hibaágai (M3, K2) egy helyi HTTP-szerverrel:
siker, nem 200-as válasz, nem JSON, nem objektum, időtúllépés, elérhetetlen
cím, megszakadt kapcsolat. Mindegyik hiba ugyanaz a kivétel (CqlServiceError)."""

import json
import socket
import threading
import time
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
        self.wfile.write(body)

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


def test_connect_timeout_is_reported_as_timeout(monkeypatch):
    """A kapcsolódás közbeni időtúllépést az urllib URLError-ba csomagolja."""
    import urllib.error
    import urllib.request

    def urlopen(*args, **kwargs):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(CqlServiceError) as error:
        evaluate({}, url="http://cql:8080")
    assert error.value.reason == "timeout"


def test_defaults_come_from_the_settings(monkeypatch):
    import urllib.request

    from app.core.config import settings

    seen = {}

    def urlopen(request, timeout):
        seen.update(url=request.full_url, timeout=timeout)
        raise ConnectionRefusedError

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(CqlServiceError):
        evaluate({})
    assert seen == {
        "url": f"{settings.cql_service_url}/evaluate",
        "timeout": settings.cql_timeout_seconds,
    }
