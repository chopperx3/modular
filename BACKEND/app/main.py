from __future__ import annotations

import datetime
import os
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from .database import Base, engine
from .middleware import add_middlewares
from .models import OCRResult
from .ocr_engine import get_reader
from .routers import ocr, results
from .routers.benchmark import router as benchmark_router
from .routers.renew import router as renew_router

Base.metadata.create_all(bind=engine)
with engine.connect() as conn:
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("ocr_results")]
    if "doc_type_id" not in cols:
        conn.execute(text("ALTER TABLE ocr_results ADD COLUMN doc_type_id INTEGER"))
        conn.commit()

app = FastAPI(
    title="MODULAR OCR API",
    version="v0.3.0",
    description=(
        "Sistema OCR inteligente para digitalización de documentos manuscritos e "
        "impresos. Combina EasyOCR (CRAFT + CRNN) y Llama 4 Scout Vision para "
        "manuscrita compleja, con métricas cuantitativas CER/WER/F1 y comparativa "
        "frente a Tesseract."
    ),
)

cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

add_middlewares(
    app,
    rate_limit_max=int(os.getenv("RATE_LIMIT_MAX", "30")),
    rate_limit_window=float(os.getenv("RATE_LIMIT_WINDOW", "60")),
)

app.include_router(ocr.router)
app.include_router(results.router)
app.include_router(renew_router)
app.include_router(benchmark_router)

@app.get("/", tags=["health"])
def root():
    return {"ok": True, "msg": "MODULAR OCR API v0.3.0"}

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "version": "v0.3.0",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "engines": {
            "easyocr": True,
            "tesseract": _tesseract_available(),
            "groq_vision": bool(os.getenv("GROQ_API_KEY", "").strip()),
        },
    }

def _tesseract_available() -> bool:
    try:
        import pytesseract
        return True
    except ImportError:
        return False

FILES_DIR = Path(__file__).resolve().parent / "out"
FILES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(FILES_DIR)), name="files")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "docs"
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")

def _warmup() -> None:
    try:
        get_reader(["es", "en"])
        print("[warmup] EasyOCR OK (es, en)")
    except Exception as e:
        print(f"[warmup] error: {e}")

@app.on_event("startup")
def startup_event() -> None:
    threading.Thread(target=_warmup, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
