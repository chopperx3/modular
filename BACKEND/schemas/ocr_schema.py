from pydantic import BaseModel, ConfigDict
from datetime import datetime

class OCRResultSchema(BaseModel):
    id: int
    filename: str
    extracted_text: str
    timestamp: datetime
    doc_type_id: int | None = None
    doc_type_label: str | None = None

    model_config = ConfigDict(from_attributes=True)
