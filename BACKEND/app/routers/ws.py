from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import os
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..cluster import cluster
from ..database import SessionLocal
from ..models import OCRResult
from ..schemas import OCRResponse
from ..ws_hub import PROTOCOL_VERSION, Connection, Job, _now_iso, hub
from .ocr import process_bytes_sync

logger = logging.getLogger("ocr.ws")

router = APIRouter(tags=["websocket"])

WS_MAX_IMAGE_MB = float(os.getenv("WS_MAX_IMAGE_MB", "10"))
WS_IDLE_TIMEOUT = float(os.getenv("WS_IDLE_TIMEOUT", "90"))
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"%PDF-", "pdf"),
)

def _detect_format(data: bytes) -> str | None:
    for sig, fmt in _SIGNATURES:
        if data.startswith(sig):
            return fmt
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None

def _error(code: str, message: str, request_id: str | None = None, **extra: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": "error", "code": code, "message": message}
    if request_id is not None:
        msg["request_id"] = request_id
    msg.update(extra)
    return msg

def _row_to_response(row: OCRResult, engine: str | None = None) -> dict[str, Any]:
    return OCRResponse(
        id=row.id,
        filename=row.filename,
        estatus=row.estatus,
        text=row.text or "",
        created_at=row.created_at,
        doc_type_id=row.doc_type_id,
        engine=engine,
        request_id=row.request_id,
        client_id=row.client_id,
        worker_id=row.worker_id,
    ).model_dump(mode="json")

def _save_row(job: Job, text: str | None, estatus: str, doc_type_id: int | None, engine: str | None,
              worker_id: str | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = OCRResult(
            filename=job.filename,
            text=text,
            estatus=estatus,
            doc_type_id=doc_type_id,
            request_id=job.request_id,
            client_id=job.client_id,
            worker_id=worker_id,
        )
        db.add(row); db.commit(); db.refresh(row)
        return _row_to_response(row, engine)
    finally:
        db.close()

def _find_row(request_id: str, client_id: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        row = db.execute(
            select(OCRResult)
            .where(OCRResult.request_id == request_id, OCRResult.client_id == client_id)
            .order_by(OCRResult.id.desc())
        ).scalars().first()
        return _row_to_response(row) if row else None
    finally:
        db.close()

def _job_message(job: Job) -> dict[str, Any]:
    if job.status == "done":
        return {"type": "result", "request_id": job.request_id, "elapsed_ms": job.elapsed_ms,
                "result": job.result, "recovered": True}
    if job.status == "error":
        return {**(job.error or _error("OCR_FAILED", "Error", job.request_id)), "recovered": True}
    return {"type": "ack", "request_id": job.request_id, "status": job.status,
            "queue_position": hub.queue_position(), "recovered": True}

async def _run_job(job: Job, data: bytes, langs: list[str], handwriting: bool, doc_type_id: int | None) -> None:
    t0 = time.perf_counter()
    ok = False
    try:
        # Con workers conectados la cola la maneja el coordinador; sin ellos, el
        # semáforo limita cuántas imágenes procesa este servidor a la vez.
        limiter = contextlib.nullcontext() if cluster.has_workers() else hub.semaphore
        async with limiter:
            job.status = "processing"
            await hub.deliver(job.client_id, {"type": "progress", "request_id": job.request_id,
                                              "stage": "recognizing"})
            try:
                text, engine, worker_id = await cluster.process(data, langs, handwriting,
                                                                local_fn=process_bytes_sync)
            except Exception as e:
                detail = e.detail if isinstance(e, HTTPException) else str(e)
                logger.warning("OCR WS falló request=%s: %s", job.request_id, detail)
                await asyncio.to_thread(_save_row, job, None, f"Error: {detail}"[:50], doc_type_id, None)
                job.status = "error"
                job.error = _error("OCR_FAILED", f"OCR falló: {detail}", job.request_id)
                await hub.deliver(job.client_id, job.error)
                return

            await hub.deliver(job.client_id, {"type": "progress", "request_id": job.request_id,
                                              "stage": "saving", "worker_id": worker_id})
            result = await asyncio.to_thread(_save_row, job, text, "Procesado", doc_type_id, engine, worker_id)
            job.elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            job.result = result
            job.status = "done"
            ok = True
            delivered = await hub.deliver(job.client_id, {
                "type": "result", "request_id": job.request_id,
                "elapsed_ms": job.elapsed_ms, "result": result,
            })
            if not delivered:
                logger.info("Cliente %s desconectado; resultado %s queda para 'resume'",
                            job.client_id, job.request_id)
            await hub.broadcast_result(result, origin_client_id=job.client_id, via="websocket")
    except Exception as e:
        logger.exception("Error inesperado en job %s", job.request_id)
        job.status = "error"
        job.error = _error("INTERNAL", f"Error interno: {e}", job.request_id)
        await hub.deliver(job.client_id, job.error)
    finally:
        hub.job_finished(ok)

async def _handle_ocr_request(conn: Connection, msg: dict[str, Any]) -> None:
    request_id = msg.get("request_id")
    if not isinstance(request_id, str) or not _ID_RE.match(request_id):
        await conn.send(_error("INVALID_REQUEST", "request_id requerido (1-64 caracteres [A-Za-z0-9_.:-])"))
        return

    existing = hub.get_job(request_id)
    if existing is not None:
        if existing.client_id != conn.client_id:
            await conn.send(_error("DUPLICATE_REQUEST", "request_id ya usado por otro cliente", request_id))
        else:
            await conn.send(_job_message(existing))
        return

    image_b64 = msg.get("image_b64")
    if not isinstance(image_b64, str) or not image_b64:
        await conn.send(_error("INVALID_REQUEST", "image_b64 requerido", request_id))
        return
    if len(image_b64) * 3 / 4 > WS_MAX_IMAGE_MB * 1024 * 1024:
        await conn.send(_error("TOO_LARGE", f"Imagen demasiado grande (>{WS_MAX_IMAGE_MB:g} MB)", request_id))
        return
    try:
        data = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError):
        await conn.send(_error("INVALID_IMAGE", "image_b64 no es base64 válido", request_id))
        return
    fmt = _detect_format(data)
    if fmt is None:
        await conn.send(_error("UNSUPPORTED_FORMAT", "Formato no soportado (PNG, JPEG, WEBP o PDF)", request_id))
        return

    if hub.queue_full():
        await conn.send(_error("BUSY", "Servidor ocupado, reintenta más tarde", request_id, retry_after_seconds=5))
        return

    lang = msg.get("lang") or "es,en"
    langs = [s.strip() for s in str(lang).split(",") if s.strip()]
    handwriting = str(msg.get("mode") or "").strip().lower() == "handwriting"
    doc_type_id = msg.get("doc_type_id")
    if doc_type_id is not None and not isinstance(doc_type_id, int):
        doc_type_id = None
    filename = str(msg.get("filename") or f"{request_id}.{fmt}")[:255]

    job = Job(request_id=request_id, client_id=conn.client_id, filename=filename)
    hub.add_job(job)
    hub.job_started()
    await conn.send({"type": "ack", "request_id": request_id, "status": "queued",
                     "queue_position": hub.queue_position(), "bytes": len(data), "format": fmt})
    hub.spawn(_run_job(job, data, langs, handwriting, doc_type_id))

async def _handle_resume(conn: Connection, msg: dict[str, Any]) -> None:
    ids = msg.get("request_ids")
    if not isinstance(ids, list):
        await conn.send(_error("INVALID_REQUEST", "request_ids debe ser una lista"))
        return
    for rid in ids[:100]:
        if not isinstance(rid, str):
            continue
        job = hub.get_job(rid)
        if job is not None and job.client_id == conn.client_id:
            await conn.send(_job_message(job))
            continue
        row = await asyncio.to_thread(_find_row, rid, conn.client_id)
        if row is not None:
            await conn.send({"type": "result", "request_id": rid, "elapsed_ms": None,
                             "result": row, "recovered": True})
        else:
            await conn.send(_error("NOT_FOUND", "Solicitud desconocida; vuelve a enviarla", rid))

async def _dispatch(conn: Connection, raw: str) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await conn.send(_error("INVALID_JSON", "El mensaje no es JSON válido"))
        return
    if not isinstance(msg, dict):
        await conn.send(_error("INVALID_JSON", "Se esperaba un objeto JSON"))
        return

    kind = msg.get("type")
    if kind == "ping":
        await conn.send({"type": "pong", "ts": msg.get("ts"), "server_time": _now_iso()})
    elif kind == "ocr_request":
        await _handle_ocr_request(conn, msg)
    elif kind == "resume":
        await _handle_resume(conn, msg)
    elif kind == "list_clients":
        await conn.send({"type": "presence", "clients_online": len(hub.online()), "clients": hub.online()})
    else:
        await conn.send(_error("UNKNOWN_TYPE", f"Tipo de mensaje desconocido: {kind!r}"))

@router.websocket("/ws/ocr")
async def ws_ocr(websocket: WebSocket):
    client_id = websocket.query_params.get("client_id") or f"anon-{uuid.uuid4().hex[:8]}"
    device = (websocket.query_params.get("device") or "desconocido")[:64]
    if not _ID_RE.match(client_id):
        await websocket.close(code=4000, reason="client_id inválido")
        return

    await websocket.accept()
    conn = Connection(ws=websocket, client_id=client_id, device=device,
                      ip=websocket.client.host if websocket.client else "unknown")
    await conn.send({
        "type": "welcome",
        "protocol_version": PROTOCOL_VERSION,
        "session_id": conn.session_id,
        "client_id": client_id,
        "server_time": _now_iso(),
        "clients_online": len(hub.online()) + 1,
        "max_image_mb": WS_MAX_IMAGE_MB,
        "idle_timeout_s": WS_IDLE_TIMEOUT,
    })
    await hub.register(conn)

    reason = "cerrado por el cliente"
    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=WS_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                reason = "inactividad"
                await conn.send(_error("IDLE_TIMEOUT", "Sin actividad; cerrando conexión"))
                await websocket.close(code=4002, reason="idle timeout")
                break
            if message["type"] == "websocket.disconnect":
                reason = f"desconexión (código {message.get('code')})"
                break
            if message.get("text") is not None:
                await _dispatch(conn, message["text"])
            else:
                await conn.send(_error("UNSUPPORTED_FRAME", "Solo se aceptan mensajes de texto JSON"))
    except WebSocketDisconnect as e:
        reason = f"desconexión (código {e.code})"
    except Exception as e:
        reason = f"error: {e}"
        logger.exception("Error en conexión WS %s", client_id)
    finally:
        await hub.unregister(conn, reason)
