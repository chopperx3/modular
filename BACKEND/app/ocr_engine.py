
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request
import urllib.error
from io import BytesIO
from pathlib import Path
from typing import Iterable, Sequence

import easyocr
import numpy as np
from PIL import Image, ImageOps

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

logger = logging.getLogger("ocr.engine")

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL   = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

_easyocr_cache: dict[tuple, easyocr.Reader] = {}

def _norm_langs(langs: Iterable[str] | None) -> tuple[str, ...]:
    base = ["es", "en"] if not langs else [s.strip().lower() for s in langs if s.strip()]
    return tuple(sorted(set(base)))

def get_reader(langs: Sequence[str] | None) -> easyocr.Reader:
    key = _norm_langs(langs)
    if key not in _easyocr_cache:
        _easyocr_cache[key] = easyocr.Reader(
            list(key),
            gpu=False,
            model_storage_directory=str(MODEL_DIR),
            download_enabled=True,
        )
    return _easyocr_cache[key]

def _image_to_base64(image_bytes: bytes) -> str:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    if max(w, h) > 1600:
        r = 1600 / max(w, h)
        img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()

def _run_groq_vision(image_bytes: bytes, max_retries: int = 4) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no configurada en .env")

    try:
        import requests
    except ImportError as e:
        raise RuntimeError("requests no esta instalado (pip install requests)") from e

    import time as _time

    b64 = _image_to_base64(image_bytes)
    payload = {
        "model": GROQ_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Transcribe exactamente el texto manuscrito de esta imagen. "
                        "Devuelve SOLO el texto tal como aparece, sin explicaciones, "
                        "sin comentarios, sin comillas. Respeta los saltos de línea."
                    )
                },
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "max_tokens": 1024,
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":   "application/json",
        "User-Agent":     "MODULAR-OCR/2.0 (https://github.com/chopperx3/modular)",
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(GROQ_URL, json=payload, headers=headers, timeout=60)
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Groq API unreachable: {e}") from e
            _time.sleep(2 ** attempt)
            continue

        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        if resp.status_code == 429:

            retry_after = resp.headers.get("Retry-After")
            try:
                wait_s = float(retry_after) if retry_after else (2 ** (attempt + 2))
            except ValueError:
                wait_s = 2 ** (attempt + 2)
            wait_s = min(wait_s, 60.0)
            if attempt < max_retries - 1:
                logger.info("Groq rate limit (429). Esperando %.1fs antes de reintentar...", wait_s)
                _time.sleep(wait_s)
                continue
            raise RuntimeError("Groq API rate limit alcanzado tras varios reintentos")

        snippet = resp.text[:200].replace("\n", " ")
        raise RuntimeError(f"Groq API error {resp.status_code}: {snippet}")

    raise RuntimeError("Groq API: agotaron los reintentos")

def _run_easyocr(image_bytes: bytes, langs: Sequence[str] | None) -> str:
    reader = get_reader(langs)
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    if max(w, h) > 2000:
        r = 2000 / max(w, h)
        img = img.resize((int(w * r), int(h * r)))
    results = reader.readtext(np.array(img), detail=0, paragraph=True)
    return "\n".join(results).strip()

def run_ocr(image_bytes: bytes, langs: Sequence[str] | None, handwriting: bool) -> tuple[str, str]:
    if handwriting:
        try:
            return _run_groq_vision(image_bytes), "groq"
        except Exception as e:
            logger.warning("Groq Vision falló, usando EasyOCR como fallback: %s", e)
            return _run_easyocr(image_bytes, langs), "easyocr (fallback)"

    return _run_easyocr(image_bytes, langs), "easyocr"
