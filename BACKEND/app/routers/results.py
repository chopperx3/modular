from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import OCRResult
from ..schemas import OCRResponse

router = APIRouter(prefix="/results", tags=["results"])


@router.get("", response_model=List[OCRResponse])
def list_results(
    db: Session = Depends(get_db),
    estatus: str | None = Query(None),
):
    # Lista resultados OCR.
    q = db.query(OCRResult).order_by(OCRResult.id.desc())
    if estatus:
        q = q.filter(OCRResult.estatus == estatus)
    return q.all()

# Detalle por id.
@router.get("/{result_id}", response_model=OCRResponse)
def get_result(result_id: int, db: Session = Depends(get_db)):
    return db.query(OCRResult).get(result_id)  # type: ignore