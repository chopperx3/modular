from sqlalchemy.orm import Session
from database import OCRResult
from datetime import datetime

def save_result(db: Session, filename: str, text: str):
    ocr_result = OCRResult(filename=filename, extracted_text=text, timestamp=datetime.utcnow())
    db.add(ocr_result)
    db.commit()
    db.refresh(ocr_result)
    return ocr_result

def get_all_results(db: Session):
    return db.query(OCRResult).all()