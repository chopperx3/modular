from transformers import TrOCRProcessor, VisionEncoderDecoderModel

# Modelo base (puedes subir a 'microsoft/trocr-large-handwritten' si tu GPU/CPU lo aguanta)
processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

# schemas/ocr_schema.py
from pydantic import BaseModel
from datetime import datetime

class OCRResultSchema(BaseModel):
    id: int
    filename: str
    extracted_text: str
    timestamp: datetime

    class Config:
        orm_mode = True
