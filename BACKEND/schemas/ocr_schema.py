from pydantic import BaseModel, ConfigDict
from datetime import datetime

class OCRResultSchema(BaseModel):
    id: int
    filename: str
    extracted_text: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)  # reemplaza a orm_mode=True en Pydantic v2
