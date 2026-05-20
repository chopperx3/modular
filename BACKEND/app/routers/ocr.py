from io import BytesIO
from typing import Sequence
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from PIL import Image, ImageOps
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import OCRResult
from ..schemas import OCRResponse
from ..ocr_engine import run_ocr

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_MB = 20
ALLOWED = {"image/png", "image/jpeg", "image/webp", "application/pdf"}

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

async def _process_bytes(data: bytes, langs: Sequence[str], handwriting: bool) -> tuple[str, str]:
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

async def _upload_core(file: UploadFile, db: Session, lang: str, mode: str, doc_type_id: int | None) -> OCRResponse:

    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=415, detail=f"Formato no soportado: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (>20MB)")

    handwriting = (mode or "").strip().lower() == "handwriting"
    langs: Sequence[str] = [s.strip() for s in (lang or "es,en").split(",") if s.strip()]

    try:
        text, engine = await _process_bytes(data, langs=langs, handwriting=handwriting)
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
        doc_type_id=doc_type_id,
    )
    db.add(row); db.commit(); db.refresh(row)

    return OCRResponse(
        id=row.id,
        filename=row.filename,
        estatus=row.estatus,
        text=row.text or "",
        created_at=row.created_at,
        doc_type_id=row.doc_type_id,
        engine=engine,
    )

@router.post("", response_model=OCRResponse, include_in_schema=False)
async def upload_image_no_slash(
    file: UploadFile = File(...), db: Session = Depends(get_db),
    lang: str = Form("es,en"), mode: str = Form(""), doc_type_id: int | None = Form(None),
):
    return await _upload_core(file, db, lang, mode, doc_type_id)

@router.post("/", response_model=OCRResponse)
async def upload_image(
    file: UploadFile = File(...), db: Session = Depends(get_db),
    lang: str = Form("es,en"), mode: str = Form(""), doc_type_id: int | None = Form(None),
):
    return await _upload_core(file, db, lang, mode, doc_type_id)
