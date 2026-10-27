"""Reconocimiento de manuscrito local con TrOCR (Transformer codificador-decodificador).

TrOCR lee una sola línea de texto por imagen, así que una página pasa por dos etapas:

1. Segmentación: el detector CRAFT (el mismo que usa EasyOCR, modelo local
   craft_mlt_25k.pth) marca las regiones con texto; las cajas se agrupan en
   renglones por solapamiento vertical y se recorta cada renglón.
2. Reconocimiento: cada recorte se redimensiona a 384x384, se divide en parches
   de 16x16 que entran al codificador (ViT/BEiT); el decodificador genera el
   texto token por token con búsqueda en haz (beam search).

Todo corre en CPU en la máquina que procesa la imagen; no hay llamadas a servicios externos.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("ocr.trocr")

MODEL_DIR = Path(__file__).resolve().parent / "models"
TROCR_MODEL = os.getenv("TROCR_MODEL", "microsoft/trocr-base-handwritten").strip()
# Búsqueda voraz (1 haz) por defecto: en IAM dio el mismo CER que 4 haces en
# menos de la mitad del tiempo en CPU.
TROCR_BEAMS = int(os.getenv("TROCR_BEAMS", "1"))
TROCR_BATCH = int(os.getenv("TROCR_BATCH", "8"))
TROCR_MAX_TOKENS = int(os.getenv("TROCR_MAX_TOKENS", "96"))

_lock = threading.Lock()
_processor = None
_model = None

@dataclass
class Line:
    box: tuple[int, int, int, int]  # x0, y0, x1, y1
    text: str = ""
    score: float | None = None      # log-probabilidad media por token del haz ganador

def detokenize(text: str) -> str:
    """Pega la puntuación a la palabra anterior.

    El modelo aprendió de IAM, cuyas transcripciones separan los signos
    ("Monday . Once"); se reescribe como texto normal ("Monday. Once").
    """
    text = re.sub(r"\s+([.,;:!?%)\]}])", r"\1", text)
    text = re.sub(r"([(\[{¿¡])\s+", r"\1", text)
    text = re.sub(r"\s*'\s*(s|t|re|ve|ll|d|m)\b", r"'\1", text)
    text = re.sub(r'"\s+(.*?)\s+"', r'"\1"', text)
    return " ".join(text.split())

def available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False

def load():
    """Carga (una sola vez por proceso) el procesador y el modelo TrOCR."""
    global _processor, _model
    with _lock:
        if _model is None:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel

            cache = str(MODEL_DIR / "trocr")
            logger.info("Cargando %s ...", TROCR_MODEL)
            _processor = TrOCRProcessor.from_pretrained(TROCR_MODEL, cache_dir=cache)
            model = VisionEncoderDecoderModel.from_pretrained(TROCR_MODEL, cache_dir=cache)
            model.eval()
            torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
            _model = model
            n = sum(p.numel() for p in model.parameters()) / 1e6
            logger.info("TrOCR listo: %s (%.0f M parámetros)", TROCR_MODEL, n)
    return _processor, _model

# ── Segmentación en renglones ────────────────────────────────────────────

def _boxes_craft(arr: np.ndarray) -> list[tuple[int, int, int, int]]:
    from .ocr_engine import get_reader

    reader = get_reader(["es", "en"])
    horizontal, free = reader.detect(
        arr, text_threshold=0.6, low_text=0.3, link_threshold=0.3,
        width_ths=1.0, ycenter_ths=0.5, height_ths=0.7, add_margin=0.08,
    )
    boxes: list[tuple[int, int, int, int]] = []
    for x0, x1, y0, y1 in horizontal[0]:
        boxes.append((int(x0), int(y0), int(x1), int(y1)))
    for poly in free[0]:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        boxes.append((int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))))
    h, w = arr.shape[:2]
    return [(max(0, a), max(0, b), min(w, c), min(h, d)) for a, b, c, d in boxes if c - a > 4 and d - b > 4]

def group_lines(boxes: list[tuple[int, int, int, int]], overlap: float = 0.5) -> list[tuple[int, int, int, int]]:
    """Agrupa cajas de palabras en renglones.

    Una caja se une a un renglón si su solapamiento vertical con él es al menos
    `overlap` de la altura menor. Devuelve los renglones de arriba hacia abajo.
    """
    lines: list[list[int]] = []  # [x0, y0, x1, y1]
    for x0, y0, x1, y1 in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        best, best_ov = None, 0.0
        for line in lines:
            inter = min(y1, line[3]) - max(y0, line[1])
            ov = inter / max(1, min(y1 - y0, line[3] - line[1]))
            if ov > best_ov:
                best, best_ov = line, ov
        if best is not None and best_ov >= overlap:
            best[0], best[1] = min(best[0], x0), min(best[1], y0)
            best[2], best[3] = max(best[2], x1), max(best[3], y1)
        else:
            lines.append([x0, y0, x1, y1])
    return [tuple(l) for l in sorted(lines, key=lambda l: l[1])]

def segment(img: Image.Image) -> list[Line]:
    arr = np.array(img)
    boxes = _boxes_craft(arr)
    if not boxes:
        return [Line((0, 0, img.width, img.height))]
    # Cada renglón se recorta a todo el ancho de la imagen: CRAFT a veces no
    # detecta palabras cortas al final ("to", "a") y quedarían fuera del recorte.
    pad = 6
    return [Line((0, max(0, y0 - pad), img.width, min(img.height, y1 + pad)))
            for _, y0, _, y1 in group_lines(boxes)]

# ── Reconocimiento ───────────────────────────────────────────────────────

def recognize_lines(crops: list[Image.Image]) -> list[tuple[str, float | None]]:
    import torch

    processor, model = load()
    out: list[tuple[str, float | None]] = []
    for i in range(0, len(crops), TROCR_BATCH):
        batch = crops[i:i + TROCR_BATCH]
        pixel_values = processor(images=batch, return_tensors="pt").pixel_values
        beams = {"num_beams": TROCR_BEAMS, "early_stopping": True} if TROCR_BEAMS > 1 else {}
        with torch.inference_mode():
            gen = model.generate(
                pixel_values,
                max_new_tokens=TROCR_MAX_TOKENS,
                return_dict_in_generate=True,
                output_scores=True,
                **beams,
            )
        texts = processor.batch_decode(gen.sequences, skip_special_tokens=True)
        scores = _mean_logprob(model, gen)
        for j, t in enumerate(texts):
            out.append((detokenize(t), scores[j] if scores is not None else None))
    return out

def _mean_logprob(model, gen) -> list[float] | None:
    """Log-probabilidad media por token de cada secuencia generada (confianza del modelo)."""
    try:
        trans = model.compute_transition_scores(
            gen.sequences, gen.scores, getattr(gen, "beam_indices", None), normalize_logits=True)
        mask = trans.isfinite() & (trans != 0)
        totals = (trans * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1)
        return [round(float(v), 4) for v in totals / counts]
    except Exception:
        return None

def _load_image(image_bytes: bytes, max_side: int = 2000) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    if max(img.size) > max_side:
        r = max_side / max(img.size)
        img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
    return img

def run_page(image_bytes: bytes) -> tuple[str, list[Line]]:
    """Transcribe una página o fragmento: segmenta en renglones y reconoce cada uno."""
    img = _load_image(image_bytes)
    lines = segment(img)
    results = recognize_lines([img.crop(l.box) for l in lines])
    for line, (text, score) in zip(lines, results):
        line.text, line.score = text, score
    text = "\n".join(l.text for l in lines if l.text)
    return text, lines

def run_trocr(image_bytes: bytes) -> str:
    return run_page(image_bytes)[0]
