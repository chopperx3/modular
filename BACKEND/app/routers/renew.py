from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
from ..database import get_db
from ..models import OCRResult
from ..renewal import renew_document, OUT_DIR

router = APIRouter(prefix="/renew", tags=["renew"])

@router.post("/{result_id}")
def renew_result(result_id: int, db: Session = Depends(get_db), doc_type_id: Optional[int] = Query(None)):
    row = db.get(OCRResult, result_id)
    if not row:
        raise HTTPException(status_code=404, detail="No encontrado")
    the_type = doc_type_id if doc_type_id is not None else row.doc_type_id
    text = row.text or ""
    docx_path, txt_path, fields, preview = renew_document(
        text=text, filename=row.filename, doc_type_id=the_type, result_id=row.id
    )
    return {
        "result_id": row.id,
        "doc_type_id": the_type,
        "url_docx": f"/files/renewed/{docx_path.name}",
        "url_txt": f"/files/renewed/{txt_path.name}",
        "fields": fields,
        "preview": preview,
    }

@router.get("/download/{kind}/{result_id}")
def download(kind: str, result_id: int):
    if kind not in {"docx","txt"}:
        raise HTTPException(status_code=400, detail="kind inválido")
    path = OUT_DIR / f"renewed_{result_id}.{kind}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No disponible")
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if kind=="docx" else "text/plain"
    return FileResponse(path, media_type=media, filename=path.name)
