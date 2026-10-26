"""Pruebas del clúster coordinador/workers sobre TCP real (127.0.0.1).

El OCR se simula con una espera (--simulate) para medir el reparto y la
tolerancia a fallos sin depender de los modelos.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
import types
from io import BytesIO
from pathlib import Path

import pytest

_DB = Path(tempfile.mkdtemp()) / "test_cluster.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["CLUSTER_PORT"] = "0"

if "easyocr" not in sys.modules:
    try:
        import easyocr  # noqa: F401
    except ImportError:
        fake = types.ModuleType("easyocr")
        fake.Reader = object
        sys.modules["easyocr"] = fake

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from fastapi import HTTPException  # noqa: E402
from PIL import Image  # noqa: E402

from app import cluster_protocol as proto  # noqa: E402
from app.cluster import Coordinator  # noqa: E402
from app.worker import Worker, _simulated_ocr  # noqa: E402

IMG = b"\x89PNG\r\n\x1a\n" + b"x" * 1000

def _local(data, langs, handwriting):
    return "texto local", "easyocr"

async def _coordinator(**kw) -> Coordinator:
    opts = dict(host="127.0.0.1", port=0, heartbeat_s=0.2, dead_after_s=1.0,
                no_worker_wait_s=1.0, local_fallback=False)
    opts.update(kw)
    c = Coordinator(**opts)
    await c.start()
    return c

async def _worker(c: Coordinator, wid: str, delay: float, slots: int = 1, **kw) -> Worker:
    w = Worker("127.0.0.1", c.port, wid, slots, ocr_fn=_simulated_ocr(delay, wid),
               reconnect=False, **kw)
    w._run_task_handle = asyncio.create_task(w.run())
    await asyncio.wait_for(w.connected.wait(), 5)
    return w

def test_reparte_entre_workers_en_paralelo():
    async def scenario():
        c = await _coordinator()
        try:
            await _worker(c, "pc-a", 0.4)
            await _worker(c, "pc-b", 0.4)
            t0 = time.perf_counter()
            results = await asyncio.gather(*(c.process(IMG, ["es"], False, _local) for _ in range(4)))
            elapsed = time.perf_counter() - t0
            return results, elapsed, c.status()
        finally:
            await c.stop()

    results, elapsed, status = asyncio.run(scenario())
    used = [wid for _, _, wid in results]
    assert sorted(used) == ["pc-a", "pc-a", "pc-b", "pc-b"]
    assert all(engine == "simulado" for _, engine, _ in results)
    # 4 tareas de 0.4 s en 2 workers: ~0.8 s, frente a 1.6 s en uno solo.
    assert elapsed < 1.3
    assert status["stats"]["completed"] == 4

def test_worker_que_se_cae_reasigna_la_tarea():
    async def scenario():
        c = await _coordinator()
        try:
            a = await _worker(c, "pc-a", 1.0)
            pending = asyncio.create_task(c.process(IMG, ["es"], False, _local))
            await asyncio.sleep(0.2)
            assert c.status()["inflight"] == 1
            a.crash()                       # cae sin despedirse
            await _worker(c, "pc-b", 0.2)
            text, engine, wid = await asyncio.wait_for(pending, 5)
            return wid, c.status()
        finally:
            await c.stop()

    wid, status = asyncio.run(scenario())
    assert wid == "pc-b"
    assert status["stats"]["reassigned"] == 1
    assert status["stats"]["workers_lost"] == 1

def test_worker_sin_latidos_se_da_por_caido():
    async def scenario():
        c = await _coordinator(dead_after_s=0.8)
        try:
            # Un "worker" que saluda y se congela: nunca manda latidos ni resultados.
            reader, writer = await asyncio.open_connection("127.0.0.1", c.port)
            await proto.write_frame(writer, {"type": proto.HELLO, "protocol_version": proto.PROTOCOL_VERSION,
                                             "worker_id": "congelado", "slots": 1})
            welcome, _ = await proto.read_frame(reader)
            assert welcome["type"] == proto.WELCOME
            pending = asyncio.create_task(c.process(IMG, ["es"], False, _local))
            await asyncio.sleep(0.2)
            assert c.status()["workers"][0]["inflight"]
            await _worker(c, "pc-b", 0.1)
            result = await asyncio.wait_for(pending, 5)
            writer.close()
            return result, c.status()
        finally:
            await c.stop()

    (_, _, wid), status = asyncio.run(scenario())
    assert wid == "pc-b"
    assert [w["worker_id"] for w in status["workers"]] == ["pc-b"]

def test_timeout_de_tarea_reasigna_a_otro_worker():
    async def scenario():
        c = await _coordinator(task_timeout_s=0.5)
        try:
            await _worker(c, "lento", 3.0)
            pending = asyncio.create_task(c.process(IMG, ["es"], False, _local))
            await asyncio.sleep(0.1)
            await _worker(c, "rapido", 0.1)
            return await asyncio.wait_for(pending, 5)
        finally:
            await c.stop()

    _, _, wid = asyncio.run(scenario())
    assert wid == "rapido"

def test_sin_workers_usa_respaldo_local_o_responde_503():
    async def scenario(fallback):
        c = await _coordinator(local_fallback=fallback, no_worker_wait_s=0.5)
        try:
            return await c.process(IMG, ["es"], False, _local)
        finally:
            await c.stop()

    assert asyncio.run(scenario(True)) == ("texto local", "easyocr", "local")
    with pytest.raises(HTTPException) as e:
        asyncio.run(scenario(False))
    assert e.value.status_code == 503
    assert "NO_WORKERS" in e.value.detail

def test_error_de_ocr_no_se_reintenta():
    async def scenario():
        c = await _coordinator()
        try:
            await _worker(c, "pc-a", 0.05)
            await _worker(c, "pc-b", 0.05)
            with pytest.raises(HTTPException) as e:
                await c.process(b"%PDF-corrupto", ["es"], False, _local)
            return e.value, c.status()
        finally:
            await c.stop()

    err, status = asyncio.run(scenario())
    assert err.status_code == 500 and "PDF corrupto" in err.detail
    assert status["stats"]["reassigned"] == 0

def test_salida_ordenada_termina_lo_pendiente():
    async def scenario():
        c = await _coordinator()
        try:
            a = await _worker(c, "pc-a", 0.6)
            pending = asyncio.create_task(c.process(IMG, ["es"], False, _local))
            await asyncio.sleep(0.2)
            await a.shutdown()
            result = await asyncio.wait_for(pending, 5)
            await asyncio.sleep(0.2)
            return result, c.status()
        finally:
            await c.stop()

    (_, _, wid), status = asyncio.run(scenario())
    assert wid == "pc-a"
    assert status["workers_online"] == 0
    assert status["stats"]["reassigned"] == 0

def test_rechaza_token_o_version_incorrectos():
    async def hello(c, **fields):
        reader, writer = await asyncio.open_connection("127.0.0.1", c.port)
        await proto.write_frame(writer, {"type": proto.HELLO, "protocol_version": proto.PROTOCOL_VERSION,
                                         "worker_id": "x", "slots": 1, **fields})
        reply, _ = await proto.read_frame(reader)
        writer.close()
        return reply

    async def scenario():
        c = await _coordinator(token="secreto")
        try:
            return (await hello(c, token="otro"), await hello(c, token="secreto", protocol_version=99),
                    await hello(c, token="secreto"))
        finally:
            await c.stop()

    bad_token, bad_version, ok = asyncio.run(scenario())
    assert bad_token["type"] == proto.REJECT and bad_token["code"] == "AUTH"
    assert bad_version["type"] == proto.REJECT and bad_version["code"] == "VERSION"
    assert ok["type"] == proto.WELCOME

def test_trama_binaria_ida_y_vuelta():
    frame = proto.encode_frame({"type": proto.TASK, "task_id": "t1"}, b"\x00\x01imagen")

    async def decode():
        reader = asyncio.StreamReader()
        reader.feed_data(frame)
        reader.feed_eof()
        return await proto.read_frame(reader)

    header, payload = asyncio.run(decode())
    assert header == {"type": proto.TASK, "task_id": "t1", "payload_len": 8}
    assert payload == b"\x00\x01imagen"

def test_api_rest_procesa_en_worker_de_otro_proceso(monkeypatch):
    """Servidor FastAPI + worker como proceso independiente conectado por TCP."""
    from fastapi.testclient import TestClient

    import app.main as main
    monkeypatch.setattr(main, "_warmup", lambda: None)

    buf = BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, format="PNG")

    with TestClient(main.app) as client:
        port = main.cluster.port
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.worker", "--coordinator", f"127.0.0.1:{port}",
             "--id", "proceso-externo", "--simulate", "0.2"],
            cwd=str(BACKEND), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 15
            while time.time() < deadline and not client.get("/cluster/status").json()["workers"]:
                time.sleep(0.1)
            status = client.get("/cluster/status").json()
            assert [w["worker_id"] for w in status["workers"]] == ["proceso-externo"]

            r = client.post("/ocr/", files={"file": ("a.png", buf.getvalue(), "image/png")})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["worker_id"] == "proceso-externo"
            assert body["engine"] == "simulado"

            saved = client.get(f"/results/{body['id']}").json()
            assert saved["worker_id"] == "proceso-externo"
        finally:
            proc.terminate()
            proc.wait(10)
