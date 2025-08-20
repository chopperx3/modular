from io import BytesIO
from pathlib import Path
from typing import Iterable, Sequence
import numpy as np
from PIL import Image, ImageOps
import easyocr

try:
    import cv2          # OPCIONAL!!!
except Exception:
    cv2 = None 

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

_reader_cache: dict[tuple[str, ...], easyocr.Reader] = {}

# Normaliza los idiomas.
def _norm_langs(langs: Iterable[str] | None) -> tuple[str, ...]:
    base = ["es", "en"] if not langs else [s.strip().lower() for s in langs if s.strip()]
    return tuple(sorted(set(base)))

# Obtiene el lector de OCR.
def get_reader(langs: Sequence[str] | None):
    key = _norm_langs(langs)
    if key not in _reader_cache:
        _reader_cache[key] = easyocr.Reader(
            list(key),
            gpu=False,
            model_storage_directory=str(MODEL_DIR),
            download_enabled=True,
        )
    return _reader_cache[key]

# Corrige inclinación si hay OpenCV.
def _deskew(gray: np.ndarray) -> np.ndarray:
    if cv2 is None:
        return gray
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr == 0))
    if coords.size == 0:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

# Preprocesa la imagen para el reconocimiento de escritura a mano.
def _preprocess_np_for_handwriting(image_bytes: bytes) -> np.ndarray:
    img = Image.open(BytesIO(image_bytes)).convert("L")
    img = ImageOps.exif_transpose(img)
    arr = np.array(img)
    arr = _deskew(arr)
    if cv2 is not None:
        arr = cv2.bitwise_not(arr)
        arr = cv2.normalize(arr, None, 0, 255, 3)
    return arr

# Ejecuta OCR con pequeños reintentos.
def run_ocr(image_bytes: bytes, langs: Sequence[str] | None, handwriting: bool) -> str:
    reader = get_reader(langs)

    def _read(np_img, paragraph, decoder, ths=None):
        kw = dict(detail=0, paragraph=paragraph, decoder=decoder)
        if ths:
            kw.update(ths)
        out = reader.readtext(np_img, **kw)
        return "\n".join(out).strip()

    if handwriting:
        np_img = _preprocess_np_for_handwriting(image_bytes)
        txt = _read(
            np_img,
            paragraph=False,
            decoder="beamsearch",
            ths=dict(contrast_ths=0.1, adjust_contrast=0.5, text_threshold=0.6, low_text=0.3),
        )
        if len(txt) < 20:
            txt = _read(np_img, paragraph=False, decoder="greedy")
        return txt

    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = ImageOps.exif_transpose(img)
    np_img = np.array(img)
    txt = _read(np_img, paragraph=True, decoder="beamsearch")
    if len(txt) < 20:
        txt = _read(np_img, paragraph=False, decoder="greedy")
    return txt
