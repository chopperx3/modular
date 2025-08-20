from pathlib import Path
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from .database import Base, engine
from .models import OCRResult
from .routers import ocr, results
from .routers.renew import router as renew_router
from .ocr_engine import get_reader


Base.metadata.create_all(bind=engine)
with engine.connect() as conn:
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("ocr_results")]
    if "doc_type_id" not in cols:
        conn.execute(text("ALTER TABLE ocr_results ADD COLUMN doc_type_id INTEGER"))
        conn.commit()

app = FastAPI(title="MODULAR OCR API", version="v0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr.router)
app.include_router(results.router)
app.include_router(renew_router)

@app.get("/")
def root():
    # Ping.
    return {"ok": True, "msg": "MODULAR OCR API"}

FILES_DIR = Path(__file__).resolve().parent / "out"
FILES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=str(FILES_DIR)), name="files")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "docs"
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")


def _warmup():
    # Carga modelos en 2º plano.
    try:
        get_reader(["es", "en"])
        print("EasyOCR warmup OK (es,en)")
    except Exception as e:  # pragma: no cover
        print("Warmup error:", e)

# Arranque
@app.on_event("startup")
def startup_event():
    threading.Thread(target=_warmup, daemon=True).start()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)