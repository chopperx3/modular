# project structure:
# ├── main.py
# ├── preprocess.py
# ├── ocr.py
# ├── utils.py
# └── requirements.txt

# requirements.txt
# fastapi
# uvicorn
# pillow
# pytesseract
# fpdf2
# opencv-python

# preprocess.py
import cv2
import numpy as np

def preprocess_image(image_data: bytes) -> np.ndarray:
    """
    Recibe bytes de imagen, devuelve imagen en escala de grises binarizada para OCR.
    """
    image = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(image, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen. Verifica el formato o los datos.")
    # binarización adaptativa
    thresh = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )
    return thresh

# ocr.py
from PIL import Image
import pytesseract
import numpy as np

def extract_text(image_array: np.ndarray) -> str:
    """
    Usa Tesseract para extraer texto de la imagen preprocesada.
    """
    # convertir numpy array a PIL Image
    pil_img = Image.fromarray(image_array)
    # OCR en español
    text = pytesseract.image_to_string(pil_img, lang='spa')
    return text

# utils.py
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF

def create_text_image(text: str, output_path: str, font_path: str = None, font_size: int = 18) -> str:
    """
    Genera una imagen con fondo blanco y texto en letra de molde.
    """
    lines = text.splitlines() or ['']
    # cargar fuente
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        font = ImageFont.load_default()
    # calcular dimensiones
    max_w = max(font.getsize(line)[0] for line in lines) + 20
    line_h = font.getsize('Hg')[1] + 10
    h = line_h * len(lines) + 20
    img = Image.new('RGB', (max_w, h), 'white')
    draw = ImageDraw.Draw(img)
    y = 10
    for line in lines:
        draw.text((10, y), line, font=font, fill='black')
        y += line_h
    img.save(output_path)
    return output_path

class PDF(FPDF):
    def add_text_page(self, text: str):
        self.add_page()
        self.set_auto_page_break(auto=True, margin=15)
        self.set_font('Arial', size=12)
        self.multi_cell(0, 10, text)

    def add_image_page(self, image_path: str):
        self.add_page()
        self.image(image_path, x=10, y=10, w=self.epw)

# main.py
import os
import tempfile
import traceback
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import preprocess
from ocr import extract_text
from utils import create_text_image, PDF

app = FastAPI(title="Manuscript Transcriber API")

@app.post("/transcribe")
async def transcribe_to_pdf(
    file: UploadFile = File(...),
    font: UploadFile = File(None)
):
    # leer bytes de imagen
    img_bytes = await file.read()
    try:
        # preprocesar imagen
        img_array = preprocess.preprocess_image(img_bytes)
        # extraer texto
        text = extract_text(img_array)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error OCR/preprocesamiento: {str(e)}")

    # crear temporal para texto y PDF
    with tempfile.TemporaryDirectory() as tmpdir:
        txt_img = os.path.join(tmpdir, "transcribed.png")
        # guardar imagen de texto
        font_path = None
        if font:
            font_data = await font.read()
            font_path = os.path.join(tmpdir, font.filename)
            with open(font_path, 'wb') as f:
                f.write(font_data)
        create_text_image(text, txt_img, font_path)
        # generar PDF
        pdf_path = os.path.join(tmpdir, "output.pdf")
        pdf = PDF()
        pdf.add_text_page(text)
        pdf.add_image_page(txt_img)
        pdf.output(pdf_path)

        return FileResponse(pdf_path, media_type='application/pdf', filename="transcription.pdf")

# To run:
# uvicorn main:app --reload
