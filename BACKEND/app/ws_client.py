"""Cliente WebSocket de línea de comandos para demostrar /ws/ocr desde otro equipo.

    python -m app.ws_client monitor --url ws://192.168.1.50:8000/ws/ocr
    python -m app.ws_client send ../manuscrita.jpg --url ws://192.168.1.50:8000/ws/ocr --handwriting
    python -m app.ws_client stress ../ejemplo.jpg -n 6 --url ws://192.168.1.50:8000/ws/ocr
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import socket
import time
import uuid
from pathlib import Path

import websockets

def _url(base: str, client_id: str) -> str:
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}client_id={client_id}&device={socket.gethostname()}-cli"

def _show(msg: dict) -> None:
    kind = msg.get("type")
    if kind == "event":
        r = msg.get("result", {})
        text = (r.get("text") or "").replace("\n", " ")[:80]
        print(f"[evento] {msg.get('event')} desde {msg.get('origin_client_id') or 'REST'}: "
              f"#{r.get('id')} {r.get('filename')} → {text!r}")
    elif kind == "presence":
        names = ", ".join(f"{c['client_id']} ({c['device']})" for c in msg.get("clients", []))
        print(f"[presencia] {msg.get('clients_online')} en línea: {names}")
    else:
        print(f"[{kind}] {json.dumps(msg, ensure_ascii=False)[:200]}")

async def monitor(url: str, client_id: str) -> None:
    delay = 1.0
    while True:
        try:
            async with websockets.connect(_url(url, client_id), max_size=None) as ws:
                delay = 1.0
                async for raw in ws:
                    _show(json.loads(raw))
        except (OSError, websockets.ConnectionClosed) as e:
            print(f"[desconectado] {e}; reintentando en {delay:.0f}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

def _request(path: Path, handwriting: bool, request_id: str | None = None) -> dict:
    return {
        "type": "ocr_request",
        "request_id": request_id or uuid.uuid4().hex,
        "filename": path.name,
        "lang": "es,en",
        "mode": "handwriting" if handwriting else "",
        "image_b64": base64.b64encode(path.read_bytes()).decode(),
    }

async def send(url: str, client_id: str, paths: list[Path], handwriting: bool) -> None:
    async with websockets.connect(_url(url, client_id), max_size=None) as ws:
        pending: dict[str, float] = {}
        for p in paths:
            req = _request(p, handwriting)
            pending[req["request_id"]] = time.perf_counter()
            await ws.send(json.dumps(req))
            print(f"[enviado] {p.name} request_id={req['request_id']}")
        while pending:
            msg = json.loads(await ws.recv())
            rid = msg.get("request_id")
            if msg["type"] == "result" and rid in pending:
                dt = (time.perf_counter() - pending.pop(rid)) * 1000
                r = msg["result"]
                print(f"[resultado] {rid} #{r['id']} motor={r.get('engine')} {dt:.0f} ms\n{r['text']}\n")
            elif msg["type"] == "error" and rid in pending:
                pending.pop(rid)
                print(f"[error] {rid} {msg['code']}: {msg['message']}")
            elif msg["type"] in ("ack", "progress"):
                print(f"[{msg['type']}] {rid} {msg.get('status') or msg.get('stage')}"
                      f"{' cola=' + str(msg['queue_position']) if 'queue_position' in msg else ''}")

async def stress(url: str, path: Path, n: int, handwriting: bool) -> None:
    t0 = time.perf_counter()
    await asyncio.gather(*(
        send(url, f"stress-{i}-{uuid.uuid4().hex[:4]}", [path], handwriting) for i in range(n)
    ))
    print(f"[stress] {n} clientes concurrentes terminados en {(time.perf_counter() - t0):.1f} s")

def main() -> None:
    ap = argparse.ArgumentParser(description="Cliente WebSocket de MODULAR OCR")
    ap.add_argument("command", choices=["monitor", "send", "stress"])
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/ocr")
    ap.add_argument("--client-id", default=f"cli-{uuid.uuid4().hex[:6]}")
    ap.add_argument("--handwriting", action="store_true")
    ap.add_argument("-n", type=int, default=5)
    a = ap.parse_args()
    try:
        if a.command == "monitor":
            asyncio.run(monitor(a.url, a.client_id))
        elif a.command == "send":
            asyncio.run(send(a.url, a.client_id, a.files, a.handwriting))
        else:
            asyncio.run(stress(a.url, a.files[0], a.n, a.handwriting))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
