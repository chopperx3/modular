from fastapi import FastAPI, File, UploadFile, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from PIL import Image
import numpy as np
import cv2
import os, io, uuid

from database import SessionLocal
from crud.ocr_results import save_result, get_all_results
from schemas.ocr_schema import OCRResultSchema

import pytesseract

# --- IMPORTANTE en Windows: ajusta la ruta a tu tesseract.exe ---
# Si ya lo tienes en PATH, puedes comentar esta línea.
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = FastAPI(title="OCR Manuscrito - Tesseract (ES)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- Preprocesado (OpenCV) ----------
def _deskew(gray: np.ndarray) -> np.ndarray:
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    if coords.size == 0:
        return gray
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    h, w = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def preprocess(path: str) -> Image.Image:
    img = cv2.imread(path)
    if img is None:
        return Image.open(path).convert("RGB")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = _deskew(gray)

    # Upscale ayuda a tesseract con trazos finos
    h, w = gray.shape[:2]
    gray = cv2.resize(gray, (int(w * 1.5), int(h * 1.5)), interpolation=cv2.INTER_CUBIC)

    # Suavizado ligero + contraste
    gray = cv2.bilateralFilter(gray, 9, 90, 90)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Binarización adaptativa
    bin_img = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )

    # Quitar líneas de guía suaves
    kernel_line = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 1))
    tophat = cv2.morphologyEx(bin_img, cv2.MORPH_TOPHAT, kernel_line)
    bin_img = cv2.subtract(bin_img, tophat)

    # Invertir si quedó muy oscuro
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)

    return Image.fromarray(bin_img).convert("RGB")

# ---------- Dependencia DB ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- OCR con Tesseract ----------
def ocr_tesseract(pil_img: Image.Image) -> str:
    # español + inglés, motor LSTM, modo una sola columna de líneas.
    config = r'--oem 1 --psm 6'
    text = pytesseract.image_to_string(pil_img, lang="spa+eng", config=config)
    return text.strip()

# ---------- Endpoints ----------
@app.post("/ocr/")
async def perform_ocr(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        ext = os.path.splitext(file.filename)[1] or ".jpg"
        tmp_name = f"{uuid.uuid4().hex}{ext}"
        tmp_path = os.path.join(UPLOAD_FOLDER, tmp_name)
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        pre = preprocess(tmp_path)
        text = ocr_tesseract(pre)

        try:
            os.remove(tmp_path)
        except Exception:
            pass

        saved = save_result(db, file.filename, text)
        return JSONResponse(content={"texto": saved.extracted_text})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/ocr/preview")
async def preview_preprocess(file: UploadFile = File(...)):
    try:
        ext = os.path.splitext(file.filename)[1] or ".jpg"
        tmp_name = f"preview_{uuid.uuid4().hex}{ext}"
        tmp_path = os.path.join(UPLOAD_FOLDER, tmp_name)
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        img_pre = preprocess(tmp_path)
        buf = io.BytesIO()
        img_pre.save(buf, format="PNG")
        buf.seek(0)

        try:
            os.remove(tmp_path)
        except Exception:
            pass

        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/registros/", response_model=list[OCRResultSchema])
def get_ocr_results(db: Session = Depends(get_db)):
    return get_all_results(db)