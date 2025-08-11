from fastapi import FastAPI, File, UploadFile, Depends, Form
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from PIL import Image
import numpy as np
import cv2
import os, io, uuid, re, math
from enum import Enum

from database import SessionLocal
from crud.ocr_results import save_result, get_all_results
from schemas.ocr_schema import OCRResultSchema

import pytesseract
# Ajusta si no lo tienes en PATH:
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ---------------------------
# App
# ---------------------------
app = FastAPI(
    title="OCR Manuscrito - Tesseract (ES) + DocType",
    version="0.4.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------
# Catálogo de tipos de documento
# (Usamos Enum para que Swagger muestre un dropdown)
# ---------------------------
class DocTypeEnum(str, Enum):
    apunte = "Apunte"
    tarea = "Tarea"
    examen = "Examen"
    recibo = "Recibo"
    carta  = "Carta"
    otro   = "Otro"

DOC_TYPES = [
    {"id": 1, "label": "Apunte"},
    {"id": 2, "label": "Tarea"},
    {"id": 3, "label": "Examen"},
    {"id": 4, "label": "Recibo"},
    {"id": 5, "label": "Carta"},
    {"id": 99, "label": "Otro"},
]

def map_doc_type(enum_value: DocTypeEnum) -> tuple[int, str]:
    label = enum_value.value
    mapping = {d["label"]: d["id"] for d in DOC_TYPES}
    return mapping.get(label, 99), label

# ---------------------------
# Utilidades de imagen
# ---------------------------
def pil_to_cv(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def cv_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))

def rotate_image_cv(img_bgr: np.ndarray, angle_deg: float) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w/2, h/2), angle_deg, 1.0)
    return cv2.warpAffine(img_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def auto_orient_osd(pil_img: Image.Image) -> Image.Image:
    """
    Usa OSD (Orientation & Script Detection) de Tesseract para
    0/90/180/270. Requiere osd.traineddata en tessdata.
    """
    try:
        osd = pytesseract.image_to_osd(pil_img)
        m = re.search(r"Rotate:\s+(\d+)", osd)
        if m:
            rot = int(m.group(1))
            if rot in (90, 180, 270):
                # PIL rota antihorario; OSD indica grados para corregir
                return pil_img.rotate(-rot, expand=True)
        return pil_img
    except Exception:
        return pil_img

def small_skew_correction(img_bgr: np.ndarray) -> np.ndarray:
    """
    Plan B: corrige inclinación leve (+/-15°) con Hough.
    No corrige 90/180/270; solo skew de escritura.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=200)
    if lines is None:
        return img_bgr

    angles = []
    for rho_theta in lines[:100]:
        rho, theta = rho_theta[0]
        angle = (theta * 180 / math.pi) - 90
        if angle < -45: angle += 90
        if angle > 45: angle -= 90
        angles.append(angle)

    if not angles:
        return img_bgr

    median = float(np.median(angles))
    if abs(median) < 0.5 or abs(median) > 15:
        return img_bgr
    return rotate_image_cv(img_bgr, median)

# ---------------------------
# Preprocesado (optimizado para manuscrita)
# ---------------------------
def preprocess(path: str) -> Image.Image:
    bgr = cv2.imread(path)
    if bgr is None:
        return Image.open(path).convert("RGB")

    # 1) Auto‑rotación (OSD) + skew leve
    pil0 = Image.open(path).convert("RGB")
    pil_oriented = auto_orient_osd(pil0)
    bgr = pil_to_cv(pil_oriented)
    bgr = small_skew_correction(bgr)

    # 2) Escala y contraste
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    gray = cv2.resize(gray, (int(w*1.6), int(h*1.6)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 9, 90, 90)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)

    # 3) Umbral adaptativo (mejor para tinta irregular)
    bin_img = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 35, 15
    )

    # 4) Limpiar ruido y reforzar trazos
    kernel = np.ones((2,2), np.uint8)
    bin_img = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, kernel, iterations=1)
    bin_img = cv2.dilate(bin_img, kernel, iterations=1)

    # Fondo blanco, texto negro
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)

    return Image.fromarray(bin_img).convert("RGB")

# ---------------------------
# OCR helpers (dos fases)
# ---------------------------
def _ocr_full_block(pil_img: Image.Image) -> str:
    # spa suele ir mejor en manuscrita; si necesitas mezcla usa spa+eng
    config = r'--oem 1 --psm 6 -l spa'
    return pytesseract.image_to_string(pil_img, config=config).strip()

def _segment_lines(img: np.ndarray) -> list[np.ndarray]:
    """Devuelve recortes por línea usando proyección horizontal."""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    bw = gray
    if bw.max() <= 1:
        bw = (bw*255).astype(np.uint8)

    # Asegurar binario (texto negro)
    _, th = cv2.threshold(bw, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if np.mean(th) > 127:
        th = cv2.bitwise_not(th)

    hist = np.sum(th > 0, axis=1)
    lines, start = [], None
    thresh = max(5, int(0.02*th.shape[1]))  # mínimo de píxeles "negros"
    for i, v in enumerate(hist):
        if v > thresh and start is None:
            start = i
        elif v <= thresh and start is not None:
            if i - start > 10:  # alto mínimo de línea
                pad = 4
                y1 = max(0, start - pad)
                y2 = min(th.shape[0], i + pad)
                lines.append((y1, y2))
            start = None
    if start is not None and th.shape[0]-start > 10:
        lines.append((start, th.shape[0]))

    crops = [bw[y1:y2, :] for (y1, y2) in lines]
    return crops

def _ocr_by_lines(pil_img: Image.Image) -> str:
    """OCR línea por línea con psm 7."""
    arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    crops = _segment_lines(arr)
    texts = []
    for c in crops:
        line = Image.fromarray(c).convert("RGB")
        txt = pytesseract.image_to_string(line, config=r'--oem 1 --psm 7 -l spa').strip()
        if txt:
            texts.append(txt)
    return "\n".join(texts).strip()

def ocr_tesseract(pil_img: Image.Image) -> str:
    # Fase A: bloque rápido
    t1 = _ocr_full_block(pil_img)
    # Si es muy corto o con muchos símbolos raros, intenta por líneas
    bad = sum(ch in "@#$%{}[]|\\/<>~^`*_=+" for ch in t1)
    if len(t1) < 25 or bad >= 5:
        t2 = _ocr_by_lines(pil_img)
        return t2 if len(t2) > len(t1) else t1
    return t1

# ---------------------------
# DB session
# ---------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------
# Endpoints
# ---------------------------
@app.post("/ocr/")
async def perform_ocr(
    file: UploadFile = File(...),
    doc_type: DocTypeEnum = Form(...),  # <— Dropdown en Swagger
    db: Session = Depends(get_db)
):
    """
    Sube una imagen, elige el tipo (dropdown) y guarda:
    - texto OCR
    - doc_type_id + doc_type_label
    """
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

        doc_type_id, doc_type_label = map_doc_type(doc_type)
        saved = save_result(db, file.filename, text, doc_type_id, doc_type_label)
        return {
            "texto": saved.extracted_text,
            "doc_type_id": saved.doc_type_id,
            "doc_type_label": saved.doc_type_label
        }
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/ocr/preview")
async def preview_preprocess(file: UploadFile = File(...)):
    """
    Devuelve PNG del preprocesado con auto‑rotación.
    Útil para verificar que no queda ladeada ni recortada.
    """
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

@app.get("/doc_types")
def list_doc_types():
    return DOC_TYPES
