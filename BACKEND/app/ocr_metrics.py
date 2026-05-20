
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image
from jiwer import wer as jiwer_wer, cer as jiwer_cer

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False

try:
    import os
    import pytesseract
    _tess_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if _tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = _tess_cmd
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False

@dataclass
class SingleResult:
    image_path: str
    ground_truth: str
    predicted_text: str
    cer: float
    wer: float
    char_precision: float
    char_recall: float
    f1: float
    latency_ms: float
    engine: str

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class BenchmarkReport:
    engine: str
    n_images: int
    mean_cer: float
    mean_wer: float
    mean_precision: float
    mean_recall: float
    mean_f1: float
    mean_latency_ms: float
    std_cer: float
    std_wer: float
    results: list[SingleResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["results"] = [r.to_dict() for r in self.results]
        return d

def _normalize(text: str) -> str:
    return " ".join(text.lower().split())

def compute_cer(reference: str, hypothesis: str) -> float:
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    try:
        return float(jiwer_cer(ref, hyp))
    except Exception:
        return 1.0

def compute_wer(reference: str, hypothesis: str) -> float:
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    try:
        return float(jiwer_wer(ref, hyp))
    except Exception:
        return 1.0

def compute_char_metrics(reference: str, hypothesis: str) -> tuple[float, float, float]:
    ref_chars = list(_normalize(reference))
    hyp_chars = list(_normalize(hypothesis))

    ref_counts: dict[str, int] = {}
    hyp_counts: dict[str, int] = {}
    for c in ref_chars:
        ref_counts[c] = ref_counts.get(c, 0) + 1
    for c in hyp_chars:
        hyp_counts[c] = hyp_counts.get(c, 0) + 1

    tp = sum(min(ref_counts.get(c, 0), hyp_counts.get(c, 0)) for c in set(ref_counts) | set(hyp_counts))
    fp = sum(max(0, hyp_counts.get(c, 0) - ref_counts.get(c, 0)) for c in set(hyp_counts))
    fn = sum(max(0, ref_counts.get(c, 0) - hyp_counts.get(c, 0)) for c in set(ref_counts))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1

def evaluate_single(
    reference: str,
    hypothesis: str,
    latency_ms: float,
    image_path: str,
    engine: str,
) -> SingleResult:
    cer = compute_cer(reference, hypothesis)
    wer = compute_wer(reference, hypothesis)
    precision, recall, f1 = compute_char_metrics(reference, hypothesis)
    return SingleResult(
        image_path=image_path,
        ground_truth=reference,
        predicted_text=hypothesis,
        cer=round(cer, 4),
        wer=round(wer, 4),
        char_precision=round(precision, 4),
        char_recall=round(recall, 4),
        f1=round(f1, 4),
        latency_ms=round(latency_ms, 1),
        engine=engine,
    )

_easyocr_reader_cache: dict[tuple, "easyocr.Reader"] = {}

def _get_easyocr_reader(langs: tuple[str, ...] = ("es", "en")) -> "easyocr.Reader":
    if not _EASYOCR_AVAILABLE:
        raise RuntimeError("EasyOCR no está instalado.")
    if langs not in _easyocr_reader_cache:
        model_dir = Path(__file__).resolve().parent / "models"
        model_dir.mkdir(exist_ok=True)
        _easyocr_reader_cache[langs] = easyocr.Reader(
            list(langs),
            gpu=False,
            model_storage_directory=str(model_dir),
            download_enabled=True,
        )
    return _easyocr_reader_cache[langs]

def run_easyocr_single(
    image_path: str | Path,
    langs: Sequence[str] = ("es", "en"),
    handwriting: bool = False,
) -> tuple[str, float]:
    reader = _get_easyocr_reader(tuple(sorted(langs)))
    img    = Image.open(image_path).convert("RGB")
    arr    = np.array(img)

    t0 = time.perf_counter()
    if handwriting:

        results = reader.readtext(
            arr,
            detail=0,
            paragraph=False,
            contrast_ths=0.1,
            adjust_contrast=0.5,
            text_threshold=0.6,
            low_text=0.3,
        )
    else:
        results = reader.readtext(arr, detail=0, paragraph=True)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    text = "\n".join(results).strip()
    return text, latency_ms

_tesseract_langs_cache: list[str] | None = None

def _tesseract_available_langs() -> list[str]:
    global _tesseract_langs_cache
    if _tesseract_langs_cache is not None:
        return _tesseract_langs_cache
    if not _TESSERACT_AVAILABLE:
        _tesseract_langs_cache = []
        return _tesseract_langs_cache
    try:
        _tesseract_langs_cache = list(pytesseract.get_languages(config=""))
    except Exception:
        _tesseract_langs_cache = []
    return _tesseract_langs_cache

def _ensure_spanish_traineddata() -> bool:
    if "spa" in _tesseract_available_langs():
        return True
    if not _TESSERACT_AVAILABLE:
        return False
    try:
        tess_cmd = pytesseract.pytesseract.tesseract_cmd
        tessdata_dir = Path(tess_cmd).resolve().parent / "tessdata"
        if not tessdata_dir.exists():
            return False
        target = tessdata_dir / "spa.traineddata"
        if target.exists():
            return True
        url = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata"
        print(f"[i] Descargando paquete de idioma 'spa' a {target} ...")

        try:
            import certifi
            import requests
            with requests.get(url, stream=True, verify=certifi.where(), timeout=60) as r:
                r.raise_for_status()
                with open(target, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
        except ImportError:

            import ssl, urllib.request
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode    = ssl.CERT_NONE
            urllib.request.urlretrieve(url, target)

        print("[i] Listo. spa.traineddata instalado.")
        global _tesseract_langs_cache
        _tesseract_langs_cache = None
        return "spa" in _tesseract_available_langs()
    except PermissionError:
        print("[!] No se pudo escribir spa.traineddata (requiere permisos de admin).")
        print("    Descargalo manualmente con un navegador y copialo a:")
        print(f"    {Path(pytesseract.pytesseract.tesseract_cmd).resolve().parent / 'tessdata'}")
        print("    URL: https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata")
        return False
    except Exception as e:
        print(f"[!] Error descargando spa.traineddata: {e}")
        print("    Descargalo manualmente y copialo a la carpeta tessdata/ de Tesseract.")
        return False

def run_groq_vision(image_path: str | Path) -> tuple[str, float]:
    from .ocr_engine import _run_groq_vision
    with open(image_path, "rb") as f:
        data = f.read()
    t0 = time.perf_counter()
    text = _run_groq_vision(data)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return text.strip(), latency_ms

def _groq_available() -> bool:
    import os
    return bool(os.getenv("GROQ_API_KEY", "").strip())

def run_tesseract_ocr(
    image_path: str | Path,
    lang: str | None = None,
) -> tuple[str, float]:
    if not _TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract no está instalado.")
    if lang is None:
        installed = set(_tesseract_available_langs())
        parts     = [code for code in ("spa", "eng") if code in installed]
        lang      = "+".join(parts) if parts else "eng"
    img = Image.open(image_path).convert("RGB")
    t0  = time.perf_counter()
    text = pytesseract.image_to_string(img, lang=lang, config="--psm 6")
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return text.strip(), latency_ms

def _tesseract_binary_works() -> bool:
    if not _TESSERACT_AVAILABLE:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

def benchmark_dataset(
    ground_truth: dict[str, str],
    base_dir: Path,
    engines: list[str] | None = None,
    max_images: int | None = None,
    handwriting_prefix: str = "handwritten",
) -> dict[str, BenchmarkReport]:
    if engines is None:
        engines = []
        if _EASYOCR_AVAILABLE:
            engines.append("easyocr")
        if _tesseract_binary_works():
            engines.append("tesseract")
        if _groq_available():
            engines.append("groq")
    else:

        if "tesseract" in engines and not _tesseract_binary_works():
            print("[!] Tesseract solicitado pero el binario no se encuentra en el sistema.")
            print("    Instalalo desde: https://github.com/UB-Mannheim/tesseract/wiki")
            print("    Excluyendo Tesseract del benchmark para no generar metricas falsas.")
            engines = [e for e in engines if e != "tesseract"]
        if "groq" in engines and not _groq_available():
            print("[!] Groq solicitado pero GROQ_API_KEY no esta configurada en .env.")
            engines = [e for e in engines if e != "groq"]

    if "tesseract" in engines:
        _ensure_spanish_traineddata()
        langs = _tesseract_available_langs()
        print(f"[i] Tesseract listo. Idiomas instalados: {langs or '(ninguno)'}")

    items = list(ground_truth.items())
    if max_images is not None:

        printed     = [(p, t) for p, t in items if handwriting_prefix not in p][:max_images]
        handwritten = [(p, t) for p, t in items if handwriting_prefix in p][:max_images]
        items       = printed + handwritten

    reports: dict[str, BenchmarkReport] = {}

    for engine in engines:
        print(f"\n{'='*60}")
        print(f"  Motor: {engine.upper()}  ({len(items)} imágenes)")
        print(f"{'='*60}")
        results: list[SingleResult] = []

        for idx, (rel_path, reference) in enumerate(items):
            image_path = base_dir / rel_path
            if not image_path.exists():
                print(f"  [!] Imagen no encontrada: {image_path}")
                continue

            is_hw = handwriting_prefix in rel_path

            try:
                if engine == "easyocr":
                    predicted, latency = run_easyocr_single(image_path, handwriting=is_hw)
                elif engine == "tesseract":
                    predicted, latency = run_tesseract_ocr(image_path)
                elif engine == "groq":
                    predicted, latency = run_groq_vision(image_path)

                    time.sleep(2.0)
                else:
                    raise ValueError(f"Motor desconocido: {engine}")
            except Exception as e:
                print(f"  [ERROR] {rel_path}: {e}")
                predicted, latency = "", 0.0

            sr = evaluate_single(reference, predicted, latency, str(rel_path), engine)
            results.append(sr)

            icon = "OK" if sr.cer < 0.15 else ("~~" if sr.cer < 0.35 else "XX")
            print(f"  [{idx+1:02d}/{len(items)}] {icon} CER={sr.cer:.3f}  WER={sr.wer:.3f}"
                  f"  F1={sr.f1:.3f}  {sr.latency_ms:.0f}ms  {rel_path}")

        if not results:
            continue

        failed = [r for r in results if r.latency_ms == 0.0]
        if len(failed) / len(results) > 0.9:
            print(
                f"\n[!] El motor '{engine}' fallo en {len(failed)}/{len(results)} imagenes. "
                f"Excluyendolo del reporte final para no contaminar metricas.\n"
                f"    Causa probable: API key invalida, binario no instalado, o cuota agotada."
            )
            continue

        valid = [r for r in results if r.latency_ms > 0.0]
        if not valid:
            print(f"\n[!] {engine}: no hubo resultados validos. Excluyendo.")
            continue

        if len(valid) < len(results):
            print(
                f"\n[i] {engine}: {len(valid)}/{len(results)} imagenes procesadas. "
                f"{len(failed)} fallos excluidos del promedio (rate limit, error, etc)."
            )

        cer_vals     = [r.cer for r in valid]
        wer_vals     = [r.wer for r in valid]
        prec_vals    = [r.char_precision for r in valid]
        recall_vals  = [r.char_recall for r in valid]
        f1_vals      = [r.f1 for r in valid]
        latency_vals = [r.latency_ms for r in valid]

        reports[engine] = BenchmarkReport(
            engine=engine,
            n_images=len(valid),
            mean_cer=round(float(np.mean(cer_vals)), 4),
            mean_wer=round(float(np.mean(wer_vals)), 4),
            mean_precision=round(float(np.mean(prec_vals)), 4),
            mean_recall=round(float(np.mean(recall_vals)), 4),
            mean_f1=round(float(np.mean(f1_vals)), 4),
            mean_latency_ms=round(float(np.mean(latency_vals)), 1),
            std_cer=round(float(np.std(cer_vals)), 4),
            std_wer=round(float(np.std(wer_vals)), 4),
            results=valid,
        )

    return reports

def print_report(reports: dict[str, BenchmarkReport]) -> None:
    SEP = "-" * 72
    print(f"\n{'='*72}")
    print("  REPORTE COMPARATIVO DE MOTORES OCR")
    print(f"{'='*72}")

    col = 14
    print(f"  {'Métrica':<22} " + "  ".join(f"{e.upper():>{col}}" for e in reports))
    print(f"  {SEP}")

    def row(label, getter):
        vals = [f"{getter(r):>{col}.4f}" for r in reports.values()]
        print(f"  {label:<22} " + "  ".join(vals))

    row("CER promedio",       lambda r: r.mean_cer)
    row("WER promedio",       lambda r: r.mean_wer)
    row("Precisión (char)",   lambda r: r.mean_precision)
    row("Recall (char)",      lambda r: r.mean_recall)
    row("F1 (char)",          lambda r: r.mean_f1)

    print(f"  {SEP}")
    for name, rep in reports.items():
        print(f"  {name.upper():<22}  Latencia media: {rep.mean_latency_ms:.1f} ms"
              f"  ±{rep.std_cer:.4f} CER std")

    if len(reports) == 2:
        engines = list(reports.values())
        delta_cer = engines[0].mean_cer - engines[1].mean_cer
        print(f"\n  -> Diferencia CER ({list(reports)[0]} vs {list(reports)[1]}): "
              f"{delta_cer:+.4f}  ({'mejor' if delta_cer < 0 else 'peor'} el primero)")

    print(f"{'='*72}\n")

def save_results(reports: dict[str, BenchmarkReport], output_path: Path) -> None:
    data = {name: rep.to_dict() for name, rep in reports.items()}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Resultados guardados en: {output_path}")

def _parse_args():
    p = argparse.ArgumentParser(description="Benchmark OCR: EasyOCR vs Tesseract")
    p.add_argument("--dataset",  default="test_images/ground_truth.json",
                   help="Ruta al ground_truth.json")
    p.add_argument("--base-dir", default="test_images",
                   help="Directorio base de las imágenes")
    p.add_argument("--engines",  nargs="+", default=None,
                   choices=["easyocr", "tesseract", "groq"],
                   help="Motores a evaluar (default: todos los disponibles)")
    p.add_argument("--max-images", type=int, default=None,
                   help="Máximo de imágenes por categoría (debug rápido)")
    p.add_argument("--output",   default="benchmark_results.json",
                   help="Archivo JSON de salida")
    return p.parse_args()

if __name__ == "__main__":
    args = _parse_args()

    gt_path  = Path(args.dataset)
    base_dir = Path(args.base_dir)

    if not gt_path.exists():
        print(f"[ERROR] No se encontró el archivo: {gt_path}")
        print("Genera las imágenes primero con:  python -m app.generate_test_images")
        sys.exit(1)

    with open(gt_path, encoding="utf-8") as f:
        ground_truth = json.load(f)

    print(f"Dataset cargado: {len(ground_truth)} imágenes")

    reports = benchmark_dataset(
        ground_truth,
        base_dir=base_dir,
        engines=args.engines,
        max_images=args.max_images,
    )

    print_report(reports)
    save_results(reports, Path(args.output))
