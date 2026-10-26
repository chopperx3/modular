from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger("ocr.ws")

PROTOCOL_VERSION = 1

def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

@dataclass
class Connection:
    ws: WebSocket
    client_id: str
    device: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    connected_at: str = field(default_factory=_now_iso)
    ip: str = "unknown"
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, message: dict[str, Any]) -> bool:
        if self.ws.client_state != WebSocketState.CONNECTED:
            return False
        try:
            async with self._lock:
                await self.ws.send_json(message)
            return True
        except Exception as e:
            logger.info("Envío fallido a %s (%s): %s", self.client_id, self.session_id, e)
            return False

    def info(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "device": self.device,
            "session_id": self.session_id,
            "connected_at": self.connected_at,
        }

@dataclass
class Job:
    request_id: str
    client_id: str
    filename: str
    status: str = "queued"
    created: float = field(default_factory=time.monotonic)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    elapsed_ms: float | None = None

class OcrHub:

    def __init__(self, max_workers: int, max_queue: int, max_jobs_cached: int = 500):
        self.max_workers = max_workers
        self.max_queue = max_queue
        self.max_jobs_cached = max_jobs_cached
        self._sessions: dict[str, Connection] = {}
        self._by_client: dict[str, Connection] = {}
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._tasks: set[asyncio.Task] = set()
        self._semaphore: asyncio.Semaphore | None = None
        self._pending = 0
        self._processed = 0
        self._failed = 0

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_workers)
        return self._semaphore

    async def register(self, conn: Connection) -> None:
        previous = self._by_client.get(conn.client_id)
        self._sessions[conn.session_id] = conn
        self._by_client[conn.client_id] = conn
        logger.info("WS conectado client=%s device=%s session=%s ip=%s (en línea: %d)",
                    conn.client_id, conn.device, conn.session_id, conn.ip, len(self._sessions))
        if previous is not None and previous.session_id != conn.session_id:
            await previous.send({"type": "error", "code": "SESSION_REPLACED",
                                 "message": "Se abrió otra conexión con el mismo client_id"})
            try:
                await previous.ws.close(code=4001, reason="replaced")
            except Exception:
                pass
        await self.broadcast_presence()

    async def unregister(self, conn: Connection, reason: str) -> None:
        self._sessions.pop(conn.session_id, None)
        if self._by_client.get(conn.client_id) is conn:
            del self._by_client[conn.client_id]
        logger.info("WS desconectado client=%s session=%s motivo=%s (en línea: %d)",
                    conn.client_id, conn.session_id, reason, len(self._sessions))
        await self.broadcast_presence()

    def online(self) -> list[dict[str, Any]]:
        return [c.info() for c in self._sessions.values()]

    def stats(self) -> dict[str, Any]:
        return {
            "path": "/ws/ocr",
            "protocol_version": PROTOCOL_VERSION,
            "clients_online": len(self._sessions),
            "jobs_pending": self._pending,
            "jobs_processed": self._processed,
            "jobs_failed": self._failed,
            "max_workers": self.max_workers,
            "max_queue": self.max_queue,
        }

    async def broadcast(self, message: dict[str, Any], exclude: str | None = None) -> None:
        targets = [c for c in list(self._sessions.values()) if c.session_id != exclude]
        if targets:
            await asyncio.gather(*(c.send(message) for c in targets))

    async def broadcast_presence(self) -> None:
        await self.broadcast({
            "type": "presence",
            "clients_online": len(self._sessions),
            "clients": self.online(),
        })

    async def broadcast_result(self, result: dict[str, Any], origin_client_id: str | None, via: str) -> None:
        origin = self._by_client.get(origin_client_id) if origin_client_id else None
        await self.broadcast({
            "type": "event",
            "event": "result_created",
            "origin_client_id": origin_client_id,
            "via": via,
            "result": result,
            "server_time": _now_iso(),
        }, exclude=origin.session_id if origin else None)

    def get_job(self, request_id: str) -> Job | None:
        return self._jobs.get(request_id)

    def add_job(self, job: Job) -> None:
        self._jobs[job.request_id] = job
        while len(self._jobs) > self.max_jobs_cached:
            oldest_id, oldest = next(iter(self._jobs.items()))
            if oldest.status in ("queued", "processing"):
                break
            del self._jobs[oldest_id]

    def capacity(self) -> int:
        from .cluster import cluster
        return max(self.max_workers, cluster.total_slots())

    def queue_full(self) -> bool:
        return self._pending >= self.capacity() + self.max_queue

    def queue_position(self) -> int:
        return max(0, self._pending - self.capacity())

    async def deliver(self, client_id: str, message: dict[str, Any]) -> bool:
        conn = self._by_client.get(client_id)
        if conn is None:
            return False
        return await conn.send(message)

    def spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def job_started(self) -> None:
        self._pending += 1

    def job_finished(self, ok: bool) -> None:
        self._pending -= 1
        if ok:
            self._processed += 1
        else:
            self._failed += 1

hub = OcrHub(
    max_workers=int(os.getenv("WS_MAX_WORKERS", "2")),
    max_queue=int(os.getenv("WS_MAX_QUEUE", "20")),
)
