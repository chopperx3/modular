from datetime import datetime
from typing import Dict
from pydantic import BaseModel

# Respuesta del OCR
class OCRResponse(BaseModel):
    id: int
    filename: str
    estatus: str
    text: str
    created_at: datetime
    doc_type_id: int | None = None

    class Config:
        from_attributes = True

# Respuesta del renovador
class RenewResponse(BaseModel):
    result_id: int
    doc_type_id: int | None = None
    url_docx: str
    url_txt: str
    fields: Dict[str, str] = {}
    preview: str