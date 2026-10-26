from typing import Sequence
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import OCRResult
from ..schemas import OCRResponse
from ..cluster import cluster
from ..pipeline import _prepare_image, process_bytes_sync  # noqa: F401
from ..ws_hub import hub

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_MB = 20
ALLOWED = {"image/png", "image/jpeg", "image/webp", "application/pdf"}

async def _process_bytes(data: bytes, langs: Sequence[str], handwriting: bool) -> tuple[str, str, str]:
    return await cluster.process(data, langs, handwriting, local_fn=process_bytes_sync)

async def _upload_core(file: UploadFile, db: Session, lang: str, mode: str, doc_type_id: int | None) -> OCRResponse:

    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=415, detail=f"Formato no soportado: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (>20MB)")

    handwriting = (mode or "").strip().lower() == "handwriting"
    langs: Sequence[str] = [s.strip() for s in (lang or "es,en").split(",") if s.strip()]

    try:
        text, engine, worker_id = await _process_bytes(data, langs=langs, handwriting=handwriting)
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
        worker_id=worker_id,
    )
    db.add(row); db.commit(); db.refresh(row)

    response = OCRResponse(
        id=row.id,
        filename=row.filename,
        estatus=row.estatus,
        text=row.text or "",
        created_at=row.created_at,
        doc_type_id=row.doc_type_id,
        engine=engine,
        worker_id=row.worker_id,
    )
    await hub.broadcast_result(response.model_dump(mode="json"), origin_client_id=None, via="rest")
    return response

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
