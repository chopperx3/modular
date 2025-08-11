from sqlalchemy.orm import Session
from database import OCRResult

def save_result(db: Session, filename: str, text: str, doc_type_id: int | None, doc_type_label: str | None):
    rec = OCRResult(
        filename=filename,
        extracted_text=text,
        doc_type_id=doc_type_id,
        doc_type_label=doc_type_label
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

def get_all_results(db: Session):
    return db.query(OCRResult).order_by(OCRResult.id.desc()).all()
