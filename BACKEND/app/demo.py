from __future__ import annotations

import argparse
import sys
from pathlib import Path

def _print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)

def _evaluate(engine: str, runner, ground_truth: str) -> dict:
    from app.ocr_metrics import compute_cer, compute_wer, compute_char_metrics

    try:
        text, latency = runner()
        ok, err = True, None
    except Exception as e:
        text, latency, ok, err = "", 0.0, False, str(e)

    metrics: dict[str, float] = {}
    if ok and ground_truth.strip():
        metrics["cer"] = compute_cer(ground_truth, text)
        metrics["wer"] = compute_wer(ground_truth, text)
        _, _, metrics["f1"] = compute_char_metrics(ground_truth, text)

    return {
        "engine":  engine,
        "ok":      ok,
        "text":    text,
        "latency": latency,
        "error":   err,
        "metrics": metrics,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Demo OCR comparativo")
    parser.add_argument("--image", required=True, help="Ruta a la imagen")
    parser.add_argument("--ground-truth", default="",
                        help="Transcripción esperada (opcional, habilita métricas)")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    if not image_path.exists():
        print(f"[X] Imagen no encontrada: {image_path}")
        return 1

    from app.ocr_metrics import (
        run_easyocr_single, run_tesseract_ocr, run_groq_vision,
        _EASYOCR_AVAILABLE, _tesseract_binary_works, _groq_available,
    )

    _print_section(f"Demo OCR comparativo  -  {image_path.name}")
    print(f"  Imagen:       {image_path}")
    if args.ground_truth.strip():
        gt_preview = args.ground_truth.strip().replace("\n", " ")
        if len(gt_preview) > 80:
            gt_preview = gt_preview[:80] + "..."
        print(f"  Ground truth: {gt_preview}")
    else:
        print("  Ground truth: (no proporcionado - no se calculan metricas)")

    results: list[dict] = []

    print("\n  [1/3] EasyOCR (CRAFT + CRNN)...")
    if _EASYOCR_AVAILABLE:
        results.append(_evaluate(
            "EasyOCR",
            lambda: run_easyocr_single(image_path, handwriting=True),
            args.ground_truth,
        ))
    else:
        print("        NO DISPONIBLE")

    print("  [2/3] Tesseract 5 (LSTM)...")
    if _tesseract_binary_works():
        results.append(_evaluate(
            "Tesseract",
            lambda: run_tesseract_ocr(image_path),
            args.ground_truth,
        ))
    else:
        print("        NO DISPONIBLE (instalar desde https://github.com/UB-Mannheim/tesseract/wiki)")

    print("  [3/3] Groq Llama 4 Scout Vision...")
    if _groq_available():
        results.append(_evaluate(
            "Groq IA",
            lambda: run_groq_vision(image_path),
            args.ground_truth,
        ))
    else:
        print("        NO DISPONIBLE (configurar GROQ_API_KEY en .env)")

    _print_section("Resultados lado a lado")
    for r in results:
        print()
        header = f"  -- {r['engine']} "
        print(header + "-" * (70 - len(header)))
        if not r["ok"]:
            print(f"  ERROR: {r['error']}")
            continue
        print(f"  Latencia: {r['latency']:.0f} ms")
        if r["metrics"]:
            m = r["metrics"]
            print(f"  CER: {m['cer']*100:.2f}%   WER: {m['wer']*100:.2f}%   F1: {m['f1']:.3f}")
        print("  Texto reconocido:")
        text = r["text"].strip() or "(vacio)"
        for line in text.split("\n"):
            print(f"    | {line}")

    valid_with_metrics = [r for r in results if r["metrics"]]
    if valid_with_metrics:
        winner = max(valid_with_metrics, key=lambda r: r["metrics"]["f1"])
        _print_section(
            f"Ganador en F1: {winner['engine']}  "
            f"(F1={winner['metrics']['f1']:.3f}, "
            f"CER={winner['metrics']['cer']*100:.2f}%)"
        )

    return 0

if __name__ == "__main__":
    sys.exit(main())
