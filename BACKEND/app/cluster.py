"""Coordinador del clúster de OCR.

El servidor FastAPI ya no reconoce las imágenes: las reparte entre nodos worker
que corren en otras computadoras y se conectan por TCP (ver cluster_protocol.py
y worker.py).

- Reparto: cada tarea va al worker con menor carga relativa (tareas en curso / slots).
- Latidos: un worker que no manda nada en `dead_after_s` se da por caído.
- Tolerancia a fallos: las tareas de un worker caído, o que exceden
  `task_timeout_s`, se reasignan a otro worker (hasta `max_attempts` intentos).
  Si dos workers devuelven la misma tarea, gana el primero.
- Sin workers: si `local_fallback` está activo, el servidor procesa la imagen él
  mismo para no perder la solicitud.
"""
from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from fastapi import HTTPException

from . import cluster_protocol as proto

logger = logging.getLogger("ocr.cluster")

LOCAL_WORKER_ID = "local"

class ClusterError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

@dataclass
class Task:
    task_id: str
    data: bytes
    langs: list[str]
    handwriting: bool
    future: asyncio.Future
    attempts: int = 0
    assigned_to: str | None = None
    sent_at: float | None = None
    created: float = field(default_factory=time.monotonic)
    history: list[str] = field(default_factory=list)

@dataclass
class WorkerConn:
    worker_id: str
    host: str
    slots: int
    engines: list[str]
    writer: asyncio.StreamWriter
    peer: str
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.monotonic)
    inflight: dict[str, Task] = field(default_factory=dict)
    draining: bool = False
    alive: bool = True
    completed: int = 0
    failed: int = 0
    busy_ms: float = 0.0
    rtt_ms: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def free(self) -> int:
        return self.slots - len(self.inflight)

    @property
    def load(self) -> float:
        return len(self.inflight) / self.slots

    async def send(self, header: dict[str, Any], payload: bytes | None = None) -> None:
        async with self._lock:
            await proto.write_frame(self.writer, header, payload)

    def info(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "host": self.host,
            "peer": self.peer,
            "slots": self.slots,
            "engines": self.engines,
            "inflight": list(self.inflight),
            "draining": self.draining,
            "completed": self.completed,
            "failed": self.failed,
            "avg_ms": round(self.busy_ms / self.completed, 1) if self.completed else None,
            "rtt_ms": self.rtt_ms,
            "last_seen_s": round(time.monotonic() - self.last_seen, 1),
            "connected_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.connected_at)),
        }

class Coordinator:

    def __init__(self, host: str = "0.0.0.0", port: int = 9000, *,
                 heartbeat_s: float = 3.0, dead_after_s: float = 10.0,
                 task_timeout_s: float = 180.0, max_attempts: int = 3,
                 no_worker_wait_s: float = 15.0, local_fallback: bool = True,
                 token: str | None = None):
        self.host = host
        self.port = port
        self.heartbeat_s = heartbeat_s
        self.dead_after_s = dead_after_s
        self.task_timeout_s = task_timeout_s
        self.max_attempts = max_attempts
        self.no_worker_wait_s = no_worker_wait_s
        self.local_fallback = local_fallback
        self.token = token or None

        self._workers: dict[str, WorkerConn] = {}
        self._queue: deque[Task] = deque()
        self._tasks: dict[str, Task] = {}
        self._wakeup: asyncio.Event | None = None
        self._server: asyncio.base_events.Server | None = None
        self._bg: set[asyncio.Task] = set()
        self._rr = itertools.count()
        self._no_workers_since: float | None = None
        self.listeners: list[Callable[[dict[str, Any]], Any]] = []
        self.stats = {"submitted": 0, "completed": 0, "failed": 0, "reassigned": 0,
                      "local_fallback": 0, "workers_lost": 0}

    # ── ciclo de vida ────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._server is not None

    async def start(self) -> None:
        self._wakeup = asyncio.Event()
        self._server = await asyncio.start_server(self._handle_conn, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        self._spawn(self._dispatch_loop())
        self._spawn(self._monitor_loop())
        logger.info("Coordinador escuchando workers en tcp://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        for w in list(self._workers.values()):
            w.writer.close()
        for t in list(self._bg):
            t.cancel()
        await asyncio.gather(*self._bg, return_exceptions=True)
        await self._server.wait_closed()
        self._server = None
        self._workers.clear()
        self._queue.clear()
        for task in list(self._tasks.values()):
            if not task.future.done():
                task.future.set_exception(ClusterError("SHUTDOWN", "Coordinador detenido"))

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    # ── API para los routers ─────────────────────────────────────────────

    def has_workers(self) -> bool:
        return any(w.alive and not w.draining for w in self._workers.values())

    def total_slots(self) -> int:
        return sum(w.slots for w in self._workers.values() if w.alive and not w.draining)

    async def process(self, data: bytes, langs: Sequence[str], handwriting: bool,
                      local_fn: Callable[[bytes, Sequence[str], bool], tuple[str, str]]
                      ) -> tuple[str, str, str]:
        """Reconoce una imagen en algún worker. Devuelve (texto, motor, worker_id)."""
        if not self.running:
            text, engine = await asyncio.to_thread(local_fn, data, langs, handwriting)
            return text, engine, LOCAL_WORKER_ID

        if not self.has_workers() and self.local_fallback:
            return await self._run_local(data, langs, handwriting, local_fn, "sin workers")

        task = Task(task_id=uuid.uuid4().hex[:16], data=data, langs=list(langs),
                    handwriting=handwriting, future=asyncio.get_running_loop().create_future())
        self._tasks[task.task_id] = task
        self.stats["submitted"] += 1
        self._enqueue(task)
        try:
            return await task.future
        except ClusterError as e:
            if e.code == "NO_WORKERS" and self.local_fallback:
                return await self._run_local(data, langs, handwriting, local_fn, str(e))
            raise HTTPException(status_code=503, detail=f"{e.code}: {e}")
        finally:
            self._tasks.pop(task.task_id, None)

    async def _run_local(self, data, langs, handwriting, local_fn, reason: str) -> tuple[str, str, str]:
        logger.warning("Procesando en el coordinador (respaldo local): %s", reason)
        self.stats["local_fallback"] += 1
        text, engine = await asyncio.to_thread(local_fn, data, langs, handwriting)
        return text, engine, LOCAL_WORKER_ID

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.running,
            "listen": f"tcp://{self.host}:{self.port}" if self.running else None,
            "protocol_version": proto.PROTOCOL_VERSION,
            "workers_online": sum(1 for w in self._workers.values() if w.alive),
            "total_slots": self.total_slots(),
            "queued": len(self._queue),
            "inflight": sum(len(w.inflight) for w in self._workers.values()),
            "workers": [w.info() for w in self._workers.values()],
            "settings": {
                "heartbeat_s": self.heartbeat_s,
                "dead_after_s": self.dead_after_s,
                "task_timeout_s": self.task_timeout_s,
                "max_attempts": self.max_attempts,
                "local_fallback": self.local_fallback,
            },
            "stats": dict(self.stats),
        }

    # ── reparto ──────────────────────────────────────────────────────────

    def _enqueue(self, task: Task, front: bool = False) -> None:
        (self._queue.appendleft if front else self._queue.append)(task)
        if self._wakeup:
            self._wakeup.set()

    def _pick_worker(self, task: Task) -> WorkerConn | None:
        candidates = [w for w in self._workers.values() if w.alive and not w.draining and w.free > 0]
        if not candidates:
            return None
        # Evita repetir en el worker que ya falló con esta tarea si hay otra opción.
        fresh = [w for w in candidates if w.worker_id not in task.history]
        pool = fresh or candidates
        # Menor carga relativa; los empates se rotan (round robin).
        turn = next(self._rr)
        n = len(pool)
        return min(enumerate(pool), key=lambda iw: (iw[1].load, (iw[0] - turn) % n))[1]

    async def _dispatch_loop(self) -> None:
        assert self._wakeup is not None
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            while self._queue:
                task = self._queue[0]
                if task.future.done():
                    self._queue.popleft()
                    continue
                worker = self._pick_worker(task)
                if worker is None:
                    break
                self._queue.popleft()
                await self._assign(task, worker)

    async def _assign(self, task: Task, worker: WorkerConn) -> None:
        task.attempts += 1
        task.assigned_to = worker.worker_id
        task.sent_at = time.monotonic()
        task.history.append(worker.worker_id)
        worker.inflight[task.task_id] = task
        logger.info("Tarea %s -> worker %s (intento %d, carga %d/%d)",
                    task.task_id, worker.worker_id, task.attempts, len(worker.inflight), worker.slots)
        try:
            await worker.send({
                "type": proto.TASK,
                "task_id": task.task_id,
                "attempt": task.attempts,
                "langs": task.langs,
                "handwriting": task.handwriting,
            }, task.data)
        except Exception as e:
            await self._worker_lost(worker, f"envío fallido: {e}")

    def _requeue(self, task: Task, reason: str) -> None:
        if task.future.done():
            return
        if task.attempts >= self.max_attempts:
            self.stats["failed"] += 1
            task.future.set_exception(ClusterError(
                "MAX_ATTEMPTS", f"La tarea falló en {task.attempts} workers ({reason})"))
            return
        self.stats["reassigned"] += 1
        logger.warning("Reasignando tarea %s (%s)", task.task_id, reason)
        task.assigned_to = None
        task.sent_at = None
        self._enqueue(task, front=True)

    # ── conexión de cada worker ──────────────────────────────────────────

    async def _handle_conn(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peername = writer.get_extra_info("peername")
        peer = f"{peername[0]}:{peername[1]}" if peername else "?"
        worker: WorkerConn | None = None
        reason = "cerró la conexión"
        try:
            header, _ = await asyncio.wait_for(proto.read_frame(reader), timeout=10)
            worker = await self._register(header, writer, peer)
            if worker is None:
                return
            while True:
                header, payload = await proto.read_frame(reader)
                worker.last_seen = time.monotonic()
                if not worker.alive:
                    break
                await self._on_message(worker, header)
                if header["type"] == proto.BYE:
                    reason = "salida ordenada"
                    break
        except asyncio.IncompleteReadError:
            pass
        except asyncio.TimeoutError:
            reason = "no envió hello"
        except proto.ProtocolError as e:
            reason = f"error de protocolo: {e}"
        except (ConnectionError, OSError) as e:
            reason = f"conexión perdida: {e}"
        finally:
            if worker is not None:
                await self._worker_lost(worker, reason)
            with contextlib.suppress(Exception):
                writer.close()

    async def _register(self, hello: dict[str, Any], writer: asyncio.StreamWriter,
                        peer: str) -> WorkerConn | None:
        async def reject(code: str, message: str) -> None:
            logger.warning("Worker rechazado desde %s: %s", peer, message)
            with contextlib.suppress(Exception):
                await proto.write_frame(writer, {"type": proto.REJECT, "code": code, "message": message})

        if hello.get("type") != proto.HELLO:
            await reject("EXPECTED_HELLO", "El primer mensaje debe ser hello")
            return None
        if hello.get("protocol_version") != proto.PROTOCOL_VERSION:
            await reject("VERSION", f"Versión de protocolo {hello.get('protocol_version')} "
                                    f"no soportada (se espera {proto.PROTOCOL_VERSION})")
            return None
        if self.token and hello.get("token") != self.token:
            await reject("AUTH", "Token de clúster inválido")
            return None
        worker_id = str(hello.get("worker_id") or "")[:64]
        slots = hello.get("slots")
        if not worker_id or not isinstance(slots, int) or not 1 <= slots <= 16:
            await reject("INVALID_HELLO", "worker_id y slots (1-16) son obligatorios")
            return None

        previous = self._workers.get(worker_id)
        if previous is not None:
            await self._worker_lost(previous, "reconectó con otra conexión")
            with contextlib.suppress(Exception):
                previous.writer.close()

        worker = WorkerConn(worker_id=worker_id, host=str(hello.get("host") or "?")[:64],
                            slots=slots, engines=list(hello.get("engines") or [])[:8],
                            writer=writer, peer=peer)
        self._workers[worker_id] = worker
        await worker.send({"type": proto.WELCOME, "protocol_version": proto.PROTOCOL_VERSION,
                           "heartbeat_s": self.heartbeat_s, "dead_after_s": self.dead_after_s,
                           "coordinator_time": time.time()})
        logger.info("Worker %s conectado desde %s (%s, %d slots)", worker_id, peer, worker.host, slots)
        self._no_workers_since = None
        await self._notify("worker_joined", worker)
        if self._wakeup:
            self._wakeup.set()
        return worker

    async def _on_message(self, worker: WorkerConn, header: dict[str, Any]) -> None:
        kind = header["type"]
        if kind == proto.HEARTBEAT:
            ts = header.get("ts")
            with contextlib.suppress(Exception):
                await worker.send({"type": proto.HEARTBEAT_ACK, "ts": ts})
            if isinstance(header.get("rtt_ms"), (int, float)):
                worker.rtt_ms = round(float(header["rtt_ms"]), 1)
        elif kind == proto.RESULT:
            task = worker.inflight.pop(str(header.get("task_id")), None) or self._tasks.get(str(header.get("task_id")))
            if task is None or task.future.done():
                logger.info("Resultado tardío/duplicado de %s para %s: se ignora",
                            worker.worker_id, header.get("task_id"))
                return
            elapsed = float(header.get("elapsed_ms") or 0.0)
            worker.completed += 1
            worker.busy_ms += elapsed
            self.stats["completed"] += 1
            task.future.set_result((str(header.get("text") or ""),
                                    str(header.get("engine") or "?"), worker.worker_id))
        elif kind == proto.TASK_ERROR:
            task = worker.inflight.pop(str(header.get("task_id")), None)
            if task is None or task.future.done():
                return
            worker.failed += 1
            self.stats["failed"] += 1
            # Error de la aplicación (imagen corrupta, PDF no soportado): reintentar
            # en otro nodo daría el mismo resultado, así que se reporta al cliente.
            status = header.get("status") if isinstance(header.get("status"), int) else 500
            task.future.set_exception(HTTPException(
                status_code=status, detail=str(header.get("message") or "Error en el worker")))
        elif kind == proto.DRAIN:
            worker.draining = True
            logger.info("Worker %s en drenado: no recibe tareas nuevas", worker.worker_id)
            await self._notify("worker_draining", worker)
        elif kind == proto.BYE:
            worker.draining = True
        else:
            logger.info("Mensaje desconocido de %s: %r", worker.worker_id, kind)
        if self._wakeup:
            self._wakeup.set()

    async def _worker_lost(self, worker: WorkerConn, reason: str) -> None:
        if not worker.alive:
            return
        worker.alive = False
        if self._workers.get(worker.worker_id) is worker:
            del self._workers[worker.worker_id]
        pending = list(worker.inflight.values())
        worker.inflight.clear()
        if reason != "salida ordenada" or pending:
            self.stats["workers_lost"] += 1
        logger.warning("Worker %s fuera (%s); %d tareas a reasignar", worker.worker_id, reason, len(pending))
        for task in pending:
            self._requeue(task, f"worker {worker.worker_id} {reason}")
        with contextlib.suppress(Exception):
            worker.writer.close()
        if not self.has_workers() and self._no_workers_since is None:
            self._no_workers_since = time.monotonic()
        await self._notify("worker_left", worker, reason=reason)

    # ── vigilancia ───────────────────────────────────────────────────────

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(min(1.0, self.heartbeat_s))
            now = time.monotonic()
            for w in list(self._workers.values()):
                if now - w.last_seen > self.dead_after_s:
                    await self._worker_lost(w, f"sin latidos por {now - w.last_seen:.1f} s")
                    continue
                for task in list(w.inflight.values()):
                    if task.sent_at is not None and now - task.sent_at > self.task_timeout_s:
                        w.inflight.pop(task.task_id, None)
                        self._requeue(task, f"excedió {self.task_timeout_s:g} s en {w.worker_id}")
            if self._queue and not self.has_workers():
                since = self._no_workers_since or now
                self._no_workers_since = since
                if now - since >= self.no_worker_wait_s:
                    while self._queue:
                        task = self._queue.popleft()
                        if not task.future.done():
                            task.future.set_exception(ClusterError(
                                "NO_WORKERS", f"Ningún worker disponible en {self.no_worker_wait_s:g} s"))
            if self._queue and self._wakeup:
                self._wakeup.set()

    async def _notify(self, event: str, worker: WorkerConn, **extra: Any) -> None:
        message = {"type": "cluster", "event": event, "worker": worker.info(),
                   "workers_online": sum(1 for w in self._workers.values() if w.alive), **extra}
        for listener in list(self.listeners):
            with contextlib.suppress(Exception):
                result = listener(message)
                if asyncio.iscoroutine(result):
                    await result

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "si", "sí", "on")

def coordinator_from_env() -> Coordinator:
    return Coordinator(
        host=os.getenv("CLUSTER_HOST", "0.0.0.0"),
        port=int(os.getenv("CLUSTER_PORT", "9000")),
        heartbeat_s=float(os.getenv("CLUSTER_HEARTBEAT_S", "3")),
        dead_after_s=float(os.getenv("CLUSTER_DEAD_AFTER_S", "10")),
        task_timeout_s=float(os.getenv("CLUSTER_TASK_TIMEOUT_S", "180")),
        max_attempts=int(os.getenv("CLUSTER_MAX_ATTEMPTS", "3")),
        no_worker_wait_s=float(os.getenv("CLUSTER_NO_WORKER_WAIT_S", "15")),
        local_fallback=_env_bool("CLUSTER_LOCAL_FALLBACK", True),
        token=os.getenv("CLUSTER_TOKEN", "").strip() or None,
    )

cluster = coordinator_from_env()
