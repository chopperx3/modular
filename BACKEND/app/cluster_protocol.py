"""Protocolo coordinador <-> worker sobre TCP.

Cada mensaje es una trama binaria:

    +-----------------+----------------------+-------------------------+
    | 4 bytes (u32 BE)| N bytes              | M bytes (opcional)      |
    | N = largo header| header JSON (UTF-8)  | payload binario         |
    +-----------------+----------------------+-------------------------+

El header siempre lleva "type". Si lleva "payload_len" = M, a continuación
vienen M bytes crudos (la imagen). Así la imagen viaja sin base64 (33 % menos
bytes que por el WebSocket de los teléfonos) y el header sigue siendo legible.
"""
from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

PROTOCOL_VERSION = 1

MAX_HEADER_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 25 * 1024 * 1024

# worker -> coordinador
HELLO = "hello"            # worker_id, host, slots, engines, protocol_version, token
HEARTBEAT = "heartbeat"    # ts, active, done
RESULT = "result"          # task_id, text, engine, elapsed_ms
TASK_ERROR = "task_error"  # task_id, code, message, status
DRAIN = "drain"            # el worker deja de aceptar tareas nuevas
BYE = "bye"                # salida ordenada; unfinished = tareas que no terminó

# coordinador -> worker
WELCOME = "welcome"        # heartbeat_s, dead_after_s, coordinator_time
REJECT = "reject"          # code, message
TASK = "task"              # task_id, attempt, langs, handwriting + payload
HEARTBEAT_ACK = "heartbeat_ack"  # ts (eco, para medir RTT)

_LEN = struct.Struct(">I")

class ProtocolError(Exception):
    pass

async def read_frame(reader: asyncio.StreamReader) -> tuple[dict[str, Any], bytes | None]:
    """Lee una trama completa. Lanza IncompleteReadError si el otro extremo cerró."""
    (header_len,) = _LEN.unpack(await reader.readexactly(_LEN.size))
    if header_len == 0 or header_len > MAX_HEADER_BYTES:
        raise ProtocolError(f"header de {header_len} bytes fuera de rango")
    try:
        header = json.loads(await reader.readexactly(header_len))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProtocolError(f"header no es JSON válido: {e}") from e
    if not isinstance(header, dict) or not isinstance(header.get("type"), str):
        raise ProtocolError("header sin campo 'type'")

    payload = None
    payload_len = header.get("payload_len")
    if payload_len is not None:
        if not isinstance(payload_len, int) or payload_len < 0 or payload_len > MAX_PAYLOAD_BYTES:
            raise ProtocolError(f"payload_len inválido: {payload_len!r}")
        payload = await reader.readexactly(payload_len)
    return header, payload

def encode_frame(header: dict[str, Any], payload: bytes | None = None) -> bytes:
    if payload is not None:
        header = {**header, "payload_len": len(payload)}
    raw = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_HEADER_BYTES:
        raise ProtocolError("header demasiado grande")
    return _LEN.pack(len(raw)) + raw + (payload or b"")

async def write_frame(writer: asyncio.StreamWriter, header: dict[str, Any],
                      payload: bytes | None = None) -> None:
    writer.write(encode_frame(header, payload))
    await writer.drain()
