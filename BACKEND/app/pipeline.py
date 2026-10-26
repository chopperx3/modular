"""Preparación de la imagen + OCR. Lo ejecutan los workers (y el servidor como respaldo local)."""
from __future__ import annotations

from io import BytesIO
from typing import Sequence

from fastapi import HTTPException
from PIL import Image, ImageOps

def _prepare_image(image_bytes: bytes) -> bytes:
    try:
        im = Image.open(BytesIO(image_bytes)).convert("RGB")
        im = ImageOps.exif_transpose(im)
        w, h = im.size
        max_side = 2000
        if max(w, h) > max_side:
            r = max_side / float(max(w, h))
            im = im.resize((int(w * r), int(h * r)))
        out = BytesIO()
        im.save(out, format="WEBP", quality=95, method=6)
        return out.getvalue()
    except Exception:
        return image_bytes

def process_bytes_sync(data: bytes, langs: Sequence[str], handwriting: bool) -> tuple[str, str]:
    from .ocr_engine import run_ocr

    if len(data) == 0:
        return "", "ninguno"
    if data[:5] == b"%PDF-":
        try:
            from pdf2image import convert_from_bytes
        except Exception as e:
            raise HTTPException(status_code=415, detail=f"PDF no soportado ({e})")
        pages = convert_from_bytes(data, dpi=220, fmt="jpeg")
        parts = []
        engines: set[str] = set()
        for pg in pages:
            out = BytesIO()
            pg.save(out, format="WEBP", quality=95, method=6)
            page_text, engine = run_ocr(out.getvalue(), langs=langs, handwriting=handwriting)
            engines.add(engine)
            parts.append(page_text)
        text = "\n\n--- PAGE BREAK ---\n\n".join(p for p in parts if p.strip())
        return text, ", ".join(sorted(engines))
    prepared = _prepare_image(data)
    return run_ocr(prepared, langs=langs, handwriting=handwriting)
