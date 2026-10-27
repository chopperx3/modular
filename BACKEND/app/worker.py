"""Nodo worker del clúster de OCR.

Se ejecuta en otra computadora de la red local y se conecta al coordinador:

    python -m app.worker --coordinator 192.168.1.10:9000 --id laptop-1 --slots 1

Recibe tareas (imagen + parámetros), corre el pipeline OCR localmente con sus
propios modelos y devuelve el texto. Manda latidos cada pocos segundos y, si
pierde la conexión, se reconecta solo con espera creciente (1 -> 30 s).
Con Ctrl+C avisa al coordinador para que reasigne lo que no terminó.

--simulate N reemplaza el OCR por una espera de N segundos (pruebas sin modelos).
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import socket
import time
from typing import Any, Callable

from . import cluster_protocol as proto

logger = logging.getLogger("ocr.worker")

OcrFn = Callable[[bytes, list[str], bool], "tuple[str, str]"]

def _real_ocr() -> OcrFn:
    from .pipeline import process_bytes_sync
    return process_bytes_sync

def _simulated_ocr(seconds: float, worker_id: str) -> OcrFn:
    def run(data: bytes, langs: list[str], handwriting: bool) -> tuple[str, str]:
        time.sleep(seconds)
        if data[:5] == b"%PDF-" and b"corrupto" in data:
            raise RuntimeError("PDF corrupto")
        return f"[{worker_id}] {len(data)} bytes", "simulado"
    return run

class Worker:

    def __init__(self, host: str, port: int, worker_id: str, slots: int = 1, *,
                 ocr_fn: OcrFn, engines: list[str] | None = None, token: str | None = None,
                 reconnect: bool = True):
        self.host = host
        self.port = port
        self.worker_id = worker_id
        self.slots = slots
        self.ocr_fn = ocr_fn
        self.engines = engines or []
        self.token = token
        self.reconnect = reconnect
        self.done = 0
        self.active: dict[str, asyncio.Task] = {}
        self.rtt_ms: float | None = None
        self.connected = asyncio.Event()
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(slots)
        self._stopping = False

    async def _send(self, header: dict[str, Any]) -> None:
        if self._writer is None:
            raise ConnectionError("sin conexión")
        async with self._lock:
            await proto.write_frame(self._writer, header)

    async def run(self) -> None:
        backoff = 1.0
        while not self._stopping:
            try:
                await self._session()
                backoff = 1.0
            except PermissionError as e:
                logger.error("El coordinador rechazó al worker: %s", e)
                return
            except (ConnectionError, OSError, asyncio.IncompleteReadError, proto.ProtocolError) as e:
                logger.warning("Conexión con el coordinador perdida: %s", e or type(e).__name__)
            finally:
                self.connected.clear()
                self._writer = None
            if not self.reconnect or self._stopping:
                return
            logger.info("Reintentando en %.0f s...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _session(self) -> None:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        self._writer = writer
        heartbeat: asyncio.Task | None = None
        try:
            await self._send({
                "type": proto.HELLO,
                "protocol_version": proto.PROTOCOL_VERSION,
                "worker_id": self.worker_id,
                "host": socket.gethostname(),
                "slots": self.slots,
                "engines": self.engines,
                "pid": os.getpid(),
                "token": self.token,
            })
            welcome, _ = await asyncio.wait_for(proto.read_frame(reader), timeout=10)
            if welcome["type"] == proto.REJECT:
                raise PermissionError(f"{welcome.get('code')}: {welcome.get('message')}")
            if welcome["type"] != proto.WELCOME:
                raise proto.ProtocolError(f"se esperaba welcome, llegó {welcome['type']}")
            interval = float(welcome.get("heartbeat_s") or 3.0)
            logger.info("Conectado a %s:%d como %s (%d slots)", self.host, self.port, self.worker_id, self.slots)
            self.connected.set()
            heartbeat = asyncio.create_task(self._heartbeat_loop(interval))

            while True:
                header, payload = await proto.read_frame(reader)
                kind = header["type"]
                if kind == proto.TASK:
                    task_id = str(header["task_id"])
                    self.active[task_id] = asyncio.create_task(self._run_task(header, payload or b""))
                elif kind == proto.HEARTBEAT_ACK:
                    ts = header.get("ts")
                    if isinstance(ts, (int, float)):
                        self.rtt_ms = (time.perf_counter() - ts) * 1000.0
        finally:
            if heartbeat:
                heartbeat.cancel()
            for t in self.active.values():
                t.cancel()
            self.active.clear()
            with contextlib.suppress(Exception):
                writer.close()

    async def _heartbeat_loop(self, interval: float) -> None:
        while True:
            with contextlib.suppress(Exception):
                await self._send({"type": proto.HEARTBEAT, "ts": time.perf_counter(),
                                  "active": len(self.active), "done": self.done,
                                  "rtt_ms": self.rtt_ms})
            await asyncio.sleep(interval)

    async def _run_task(self, header: dict[str, Any], data: bytes) -> None:
        task_id = str(header["task_id"])
        langs = [str(x) for x in header.get("langs") or ["es", "en"]]
        handwriting = bool(header.get("handwriting"))
        try:
            async with self._sem:
                logger.info("Tarea %s: %d bytes, %s, intento %s", task_id, len(data),
                            "manuscrito" if handwriting else "impreso", header.get("attempt"))
                t0 = time.perf_counter()
                try:
                    text, engine = await asyncio.to_thread(self.ocr_fn, data, langs, handwriting)
                except Exception as e:
                    status = getattr(e, "status_code", 500)
                    detail = getattr(e, "detail", None) or str(e)
                    logger.warning("Tarea %s falló: %s", task_id, detail)
                    await self._send({"type": proto.TASK_ERROR, "task_id": task_id,
                                      "code": "OCR_FAILED", "status": status, "message": str(detail)})
                    return
                elapsed = round((time.perf_counter() - t0) * 1000.0, 1)
                self.done += 1
                await self._send({"type": proto.RESULT, "task_id": task_id, "text": text,
                                  "engine": engine, "elapsed_ms": elapsed})
                logger.info("Tarea %s lista en %.0f ms (%s)", task_id, elapsed, engine)
        except (ConnectionError, OSError) as e:
            logger.warning("No se pudo entregar %s: %s (el coordinador la reasignará)", task_id, e)
        finally:
            self.active.pop(task_id, None)

    async def shutdown(self, drain_timeout: float = 30.0) -> None:
        """Salida ordenada: deja de recibir tareas, termina las que tiene y se despide."""
        self._stopping = True
        if self._writer is None:
            return
        with contextlib.suppress(Exception):
            await self._send({"type": proto.DRAIN})
            pending = list(self.active.values())
            if pending:
                logger.info("Terminando %d tareas antes de salir...", len(pending))
                await asyncio.wait(pending, timeout=drain_timeout)
            await self._send({"type": proto.BYE, "unfinished": list(self.active)})
            self._writer.close()

    def crash(self) -> None:
        """Corta la conexión sin despedirse (para simular una caída en las pruebas)."""
        self._stopping = True
        if self._writer is not None:
            self._writer.transport.abort()

def main() -> None:
    parser = argparse.ArgumentParser(description="Nodo worker del clúster MODULAR OCR")
    parser.add_argument("--coordinator", default=os.getenv("CLUSTER_COORDINATOR", "127.0.0.1:9000"),
                        help="IP:puerto del coordinador (por defecto 127.0.0.1:9000)")
    parser.add_argument("--id", default=os.getenv("WORKER_ID") or socket.gethostname(),
                        help="Nombre único del worker (por defecto el nombre del equipo)")
    parser.add_argument("--slots", type=int, default=int(os.getenv("WORKER_SLOTS", "1")),
                        help="Imágenes que procesa a la vez")
    parser.add_argument("--token", default=os.getenv("CLUSTER_TOKEN") or None)
    parser.add_argument("--simulate", type=float, default=None, metavar="SEGUNDOS",
                        help="No cargar modelos: simular el OCR con una espera")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s",
                        datefmt="%H:%M:%S")
    host, _, port = args.coordinator.rpartition(":")
    if not host or not port.isdigit():
        parser.error("--coordinator debe tener la forma IP:PUERTO")

    if args.simulate is not None:
        ocr_fn, engines = _simulated_ocr(args.simulate, args.id), ["simulado"]
    else:
        logger.info("Cargando modelos OCR...")
        ocr_fn = _real_ocr()
        from .ocr_engine import GROQ_API_KEY, HANDWRITING_ENGINE, get_reader
        get_reader(["es", "en"])
        engines = ["easyocr"]
        if HANDWRITING_ENGINE in ("trocr", "groq"):
            from . import trocr_engine
            if trocr_engine.available():
                trocr_engine.load()
                engines.append("trocr")
        if GROQ_API_KEY and HANDWRITING_ENGINE == "groq":
            engines.append("groq")
        logger.info("Modelos listos: %s", ", ".join(engines))

    async def _main() -> None:
        worker = Worker(host, int(port), args.id, args.slots, ocr_fn=ocr_fn,
                        engines=engines, token=args.token)
        run_task = asyncio.create_task(worker.run())
        try:
            await asyncio.shield(run_task)
        except asyncio.CancelledError:
            # Ctrl+C: despedirse antes de cortar para que el coordinador no espere al timeout.
            await worker.shutdown(drain_timeout=10)
            run_task.cancel()
            with contextlib.suppress(BaseException):
                await run_task
            raise

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
    logger.info("Worker detenido")

if __name__ == "__main__":
    main()
