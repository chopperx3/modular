
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

APP_DIR        = Path(__file__).resolve().parent.parent
TEST_IMG_DIR   = APP_DIR / "test_images"
GT_PATH        = TEST_IMG_DIR / "ground_truth.json"
RESULTS_PATH   = APP_DIR / "benchmark_results.json"

_benchmark_status: dict = {"running": False, "last_started": None, "message": "Sin ejecuciones aún"}

class BenchmarkStatus(BaseModel):
    running: bool
    last_started: str | None
    message: str

class SingleEvalResponse(BaseModel):
    filename: str
    ground_truth_provided: bool
    easyocr_text: str
    easyocr_cer: float | None
    easyocr_wer: float | None
    easyocr_f1: float | None
    easyocr_latency_ms: float
    tesseract_text: str
    tesseract_cer: float | None
    tesseract_wer: float | None
    tesseract_f1: float | None
    tesseract_latency_ms: float

def _run_benchmark_task(max_images: int | None = None):
    global _benchmark_status
    _benchmark_status["running"] = True
    _benchmark_status["message"] = "En progreso..."

    try:
        from ..generate_test_images import generate_all
        from ..ocr_metrics import benchmark_dataset, save_results, print_report

        if not GT_PATH.exists():
            _benchmark_status["message"] = "Generando imágenes de prueba..."
            generate_all()

        with open(GT_PATH, encoding="utf-8") as f:
            ground_truth = json.load(f)

        _benchmark_status["message"] = f"Evaluando {len(ground_truth)} imágenes..."

        reports = benchmark_dataset(
            ground_truth,
            base_dir=TEST_IMG_DIR,
            max_images=max_images,
        )
        print_report(reports)
        save_results(reports, RESULTS_PATH)

        _benchmark_status["message"] = (
            f"Completado. {len(ground_truth)} imágenes evaluadas. "
            f"Resultados en benchmark_results.json"
        )
    except Exception as e:
        _benchmark_status["message"] = f"Error: {e}"
    finally:
        _benchmark_status["running"] = False

@router.post("/run", response_model=BenchmarkStatus, summary="Ejecutar benchmark completo")
async def run_benchmark(
    background_tasks: BackgroundTasks,
    max_images: Annotated[int | None, Query(description="Máximo imágenes por categoría (debug)")] = None,
):
    if _benchmark_status["running"]:
        raise HTTPException(status_code=409, detail="Ya hay un benchmark en ejecución.")

    import datetime
    _benchmark_status["last_started"] = datetime.datetime.utcnow().isoformat() + "Z"
    _benchmark_status["message"] = "Iniciando..."
    background_tasks.add_task(_run_benchmark_task, max_images)

    return BenchmarkStatus(**_benchmark_status)

@router.get("/status", response_model=BenchmarkStatus, summary="Estado del benchmark")
async def benchmark_status():
    return BenchmarkStatus(**_benchmark_status)

@router.get("/results", summary="Resultados del último benchmark")
async def get_results():
    if not RESULTS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No hay resultados aún. Ejecuta POST /benchmark/run primero.",
        )
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)

@router.post("/single", response_model=SingleEvalResponse, summary="Evaluar imagen individual")
async def evaluate_single_image(
    file: UploadFile = File(...),
    ground_truth: str | None = Query(None, description="Texto esperado para calcular métricas"),
):
    import tempfile, os
    from ..ocr_metrics import (
        run_easyocr_single, run_tesseract_ocr,
        compute_cer, compute_wer, compute_char_metrics,
    )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Archivo vacío.")

    suffix = Path(file.filename or "img.jpg").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:

        try:
            ez_text, ez_latency = run_easyocr_single(tmp_path)
        except Exception as e:
            ez_text, ez_latency = f"[Error EasyOCR: {e}]", 0.0

        try:
            tess_text, tess_latency = run_tesseract_ocr(tmp_path)
        except Exception as e:
            tess_text, tess_latency = f"[Error Tesseract: {e}]", 0.0

        ez_cer = ez_wer = ez_f1 = None
        tess_cer = tess_wer = tess_f1 = None

        if ground_truth:
            ez_cer   = compute_cer(ground_truth, ez_text)
            ez_wer   = compute_wer(ground_truth, ez_text)
            _, _, ez_f1 = compute_char_metrics(ground_truth, ez_text)
            tess_cer = compute_cer(ground_truth, tess_text)
            tess_wer = compute_wer(ground_truth, tess_text)
            _, _, tess_f1 = compute_char_metrics(ground_truth, tess_text)

        return SingleEvalResponse(
            filename=file.filename or "unknown",
            ground_truth_provided=ground_truth is not None,
            easyocr_text=ez_text,
            easyocr_cer=round(ez_cer, 4) if ez_cer is not None else None,
            easyocr_wer=round(ez_wer, 4) if ez_wer is not None else None,
            easyocr_f1=round(ez_f1, 4) if ez_f1 is not None else None,
            easyocr_latency_ms=round(ez_latency, 1),
            tesseract_text=tess_text,
            tesseract_cer=round(tess_cer, 4) if tess_cer is not None else None,
            tesseract_wer=round(tess_wer, 4) if tess_wer is not None else None,
            tesseract_f1=round(tess_f1, 4) if tess_f1 is not None else None,
            tesseract_latency_ms=round(tess_latency, 1),
        )
    finally:
        os.unlink(tmp_path)
