import base64
import os
import sys
import tempfile
import threading
import time
import types
from io import BytesIO
from pathlib import Path

import pytest

_DB = Path(tempfile.mkdtemp()) / "test_ws.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ.setdefault("WS_MAX_WORKERS", "2")

if "easyocr" not in sys.modules:
    try:
        import easyocr  # noqa: F401
    except ImportError:
        fake = types.ModuleType("easyocr")
        fake.Reader = object
        sys.modules["easyocr"] = fake

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import app.main as main  # noqa: E402
from app.routers import ws as ws_router  # noqa: E402

_active = 0
_max_active = 0
_lock = threading.Lock()

def _fake_ocr(data, langs, handwriting):
    global _active, _max_active
    with _lock:
        _active += 1
        _max_active = max(_max_active, _active)
    try:
        time.sleep(0.3)
        if data[:5] == b"%PDF-":
            raise RuntimeError("PDF corrupto")
        return f"texto {len(data)}", "groq" if handwriting else "easyocr"
    finally:
        with _lock:
            _active -= 1

@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(ws_router, "process_bytes_sync", _fake_ocr)
    monkeypatch.setattr(main, "_warmup", lambda: None)
    ws_router.hub._semaphore = None

@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c

def _png_b64() -> str:
    buf = BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def _recv_until(ws, kind, request_id=None):
    seen = []
    while True:
        msg = ws.receive_json()
        seen.append(msg)
        if msg["type"] == kind and (request_id is None or msg.get("request_id") == request_id):
            return msg, seen

def test_welcome_and_ping(client):
    with client.websocket_connect("/ws/ocr?client_id=tel-a&device=Pixel") as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["client_id"] == "tel-a"
        ws.send_json({"type": "ping", "ts": 123})
        pong, _ = _recv_until(ws, "pong")
        assert pong["ts"] == 123

def test_ocr_request_flow_and_broadcast(client):
    with client.websocket_connect("/ws/ocr?client_id=tel-a") as a, \
         client.websocket_connect("/ws/ocr?client_id=pc-monitor") as b:
        a.receive_json(); b.receive_json()
        a.send_json({"type": "ocr_request", "request_id": "r1", "filename": "nota.png",
                     "image_b64": _png_b64(), "mode": "handwriting"})
        ack, _ = _recv_until(a, "ack", "r1")
        assert ack["status"] == "queued"
        result, seen = _recv_until(a, "result", "r1")
        stages = [m["stage"] for m in seen if m["type"] == "progress"]
        assert stages == ["recognizing", "saving"]
        assert result["result"]["engine"] == "groq"
        assert result["result"]["request_id"] == "r1"
        assert result["result"]["filename"] == "nota.png"

        event, _ = _recv_until(b, "event")
        assert event["event"] == "result_created"
        assert event["origin_client_id"] == "tel-a"
        assert event["result"]["id"] == result["result"]["id"]

def test_concurrent_requests_are_parallel_and_limited(client):
    global _max_active
    _max_active = 0
    with client.websocket_connect("/ws/ocr?client_id=tel-b") as ws:
        ws.receive_json()
        img = _png_b64()
        for i in range(4):
            ws.send_json({"type": "ocr_request", "request_id": f"c{i}", "image_b64": img})
        done = set()
        while len(done) < 4:
            msg = ws.receive_json()
            if msg["type"] == "result":
                done.add(msg["request_id"])
        assert done == {"c0", "c1", "c2", "c3"}
    assert _max_active == 2

def test_errors(client):
    with client.websocket_connect("/ws/ocr?client_id=tel-c") as ws:
        ws.receive_json()
        ws.send_text("no es json")
        assert _recv_until(ws, "error")[0]["code"] == "INVALID_JSON"
        ws.send_json({"type": "desconocido"})
        assert _recv_until(ws, "error")[0]["code"] == "UNKNOWN_TYPE"
        ws.send_json({"type": "ocr_request", "image_b64": _png_b64()})
        assert _recv_until(ws, "error")[0]["code"] == "INVALID_REQUEST"
        ws.send_json({"type": "ocr_request", "request_id": "e1", "image_b64": "%%%"})
        assert _recv_until(ws, "error")[0]["code"] == "INVALID_IMAGE"
        ws.send_json({"type": "ocr_request", "request_id": "e2",
                      "image_b64": base64.b64encode(b"hola mundo").decode()})
        assert _recv_until(ws, "error")[0]["code"] == "UNSUPPORTED_FORMAT"
        ws.send_json({"type": "ocr_request", "request_id": "e3",
                      "image_b64": base64.b64encode(b"%PDF-1.4 roto").decode()})
        err, _ = _recv_until(ws, "error", "e3")
        assert err["code"] == "OCR_FAILED"
        ws.send_bytes(b"\x00\x01")
        assert _recv_until(ws, "error")[0]["code"] == "UNSUPPORTED_FRAME"

def test_result_recovered_after_disconnect(client):
    with client.websocket_connect("/ws/ocr?client_id=tel-d") as ws:
        ws.receive_json()
        ws.send_json({"type": "ocr_request", "request_id": "d1", "image_b64": _png_b64()})
        _recv_until(ws, "ack", "d1")
    time.sleep(0.8)
    with client.websocket_connect("/ws/ocr?client_id=tel-d") as ws:
        ws.receive_json()
        ws.send_json({"type": "resume", "request_ids": ["d1", "nunca"]})
        res, _ = _recv_until(ws, "result", "d1")
        assert res["recovered"] is True
        assert res["result"]["request_id"] == "d1"
        err, _ = _recv_until(ws, "error", "nunca")
        assert err["code"] == "NOT_FOUND"

def test_resend_same_request_is_idempotent(client):
    with client.websocket_connect("/ws/ocr?client_id=tel-e") as ws:
        ws.receive_json()
        ws.send_json({"type": "ocr_request", "request_id": "i1", "image_b64": _png_b64()})
        first, _ = _recv_until(ws, "result", "i1")
        ws.send_json({"type": "ocr_request", "request_id": "i1", "image_b64": _png_b64()})
        again, _ = _recv_until(ws, "result", "i1")
        assert again["result"]["id"] == first["result"]["id"]
    with client.websocket_connect("/ws/ocr?client_id=otro") as ws:
        ws.receive_json()
        ws.send_json({"type": "ocr_request", "request_id": "i1", "image_b64": _png_b64()})
        assert _recv_until(ws, "error", "i1")[0]["code"] == "DUPLICATE_REQUEST"

def test_recovery_from_database_after_restart(client):
    with client.websocket_connect("/ws/ocr?client_id=tel-f") as ws:
        ws.receive_json()
        ws.send_json({"type": "ocr_request", "request_id": "f1", "image_b64": _png_b64()})
        _recv_until(ws, "result", "f1")
    ws_router.hub._jobs.clear()
    with client.websocket_connect("/ws/ocr?client_id=tel-f") as ws:
        ws.receive_json()
        ws.send_json({"type": "resume", "request_ids": ["f1"]})
        res, _ = _recv_until(ws, "result", "f1")
        assert res["result"]["request_id"] == "f1"

def test_health_reports_websocket(client):
    with client.websocket_connect("/ws/ocr?client_id=tel-g") as ws:
        ws.receive_json()
        h = client.get("/health").json()
        assert h["websocket"]["clients_online"] >= 1

def test_rest_upload_is_broadcast_to_sockets(client, monkeypatch):
    from app.routers import ocr as ocr_router
    monkeypatch.setattr(ocr_router, "process_bytes_sync", _fake_ocr)
    with client.websocket_connect("/ws/ocr?client_id=pc-monitor-2") as ws:
        ws.receive_json()
        r = client.post("/ocr/", files={"file": ("a.png", base64.b64decode(_png_b64()), "image/png")})
        assert r.status_code == 200
        event, _ = _recv_until(ws, "event")
        assert event["via"] == "rest"
        assert event["result"]["id"] == r.json()["id"]
