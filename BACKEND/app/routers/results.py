from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..database import get_db
from ..models import OCRResult
from ..schemas import OCRResponse

router = APIRouter(prefix="/results", tags=["results"])

@router.get("", response_model=List[OCRResponse])
def list_results(
    db: Session = Depends(get_db),
    estatus: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    stmt = select(OCRResult).order_by(OCRResult.id.desc()).limit(limit)
    if estatus:
        stmt = stmt.filter(OCRResult.estatus == estatus)
    return db.execute(stmt).scalars().all()

@router.get("/{result_id}", response_model=OCRResponse)
def get_result(result_id: int, db: Session = Depends(get_db)):
    row = db.get(OCRResult, result_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Resultado no encontrado")
    return row

@router.delete("/{result_id}", status_code=204)
def delete_result(result_id: int, db: Session = Depends(get_db)):
    row = db.get(OCRResult, result_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Resultado no encontrado")
    db.delete(row)
    db.commit()
    return None
