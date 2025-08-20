from io import BytesIO
from typing import Sequence
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from PIL import Image, ImageOps
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import OCRResult
from ..schemas import OCRResponse
from ..ocr_engine import run_ocr

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_MB = 20
ALLOWED = {"image/png", "image/jpeg", "image/webp", "application/pdf"}

# Prepara la imagen para OCR.
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

# Procesa los bytes de imagen o PDF.
async def _process_bytes(data: bytes, langs: Sequence[str], handwriting: bool) -> str:
    if len(data) == 0:
        return ""
    text: str
    if data[:5] == b"%PDF-":  # PDF rápido
        try:
            from pdf2image import convert_from_bytes  # type: ignore
        except Exception as e:  # pragma: no cover
            raise HTTPException(status_code=415, detail=f"PDF no soportado ({e})")
        pages = convert_from_bytes(data, dpi=220, fmt="jpeg")
        parts = []
        for pg in pages:
            out = BytesIO()
            pg.save(out, format="WEBP", quality=95, method=6)
            parts.append(run_ocr(out.getvalue(), langs=langs, handwriting=handwriting))
        text = "\n\n--- PAGE BREAK ---\n\n".join(p for p in parts if p.strip())
    else:
        prepared = _prepare_image(data)
        text = run_ocr(prepared, langs=langs, handwriting=handwriting)
    return text

async def _upload_core(file: UploadFile, db: Session, lang: str, mode: str, doc_type_id: int | None) -> OCRResponse:
    # Núcleo de subida.
    # Validación de archivo
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=415, detail=f"Formato no soportado: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (>20MB)")

    handwriting = (mode or "").strip().lower() == "handwriting"
    langs: Sequence[str] = [s.strip() for s in (lang or "es,en").split(",") if s.strip()]

    try:
        text = await _process_bytes(data, langs=langs, handwriting=handwriting)
    except HTTPException:
        raise
    except Exception as e:
        row = OCRResult(filename=file.filename, text=None, estatus=f"Error: {e}", doc_type_id=doc_type_id)
        db.add(row); db.commit(); db.refresh(row)
        raise HTTPException(status_code=500, detail=f"OCR falló: {e}")

    row = OCRResult(
    filename=file.filename,
    text=text,
    estatus="Procesado",
    doc_type_id=doc_type_id
)
    db.add(row); db.commit(); db.refresh(row)

    return OCRResponse(
        id=row.id,
        filename=row.filename,
        estatus=row.estatus,
        text=row.text or "",
        created_at=row.created_at,
        doc_type_id=row.doc_type_id,
    )

@router.post("", response_model=OCRResponse, include_in_schema=False)
async def upload_image_no_slash(
    file: UploadFile = File(...), db: Session = Depends(get_db),
    lang: str = Query("es,en"), mode: str = Query(""), doc_type_id: int | None = Query(None),
):
    # Subida sin barra final.
    return await _upload_core(file, db, lang, mode, doc_type_id)

@router.post("/", response_model=OCRResponse)
async def upload_image(
    file: UploadFile = File(...), db: Session = Depends(get_db),
    lang: str = Query("es,en"), mode: str = Query(""), doc_type_id: int | None = Query(None),
):
    # Subida principal.
    return await _upload_core(file, db, lang, mode, doc_type_id)