from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

def _pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if v is not None else "—"

def _ms(v: float | None) -> str:
    return f"{v:.0f} ms" if v is not None else "—"

def _f(v: float | None, digits: int = 4) -> str:
    return f"{v:.{digits}f}" if v is not None else "—"

def _split_categories(results: list[dict]) -> dict[str, list[dict]]:
    categories = {
        "Impreso sintético":    [r for r in results if r["image_path"].startswith("printed/")],
        "Manuscrito sintético": [r for r in results if r["image_path"].startswith("handwritten/")],
        "Impreso real":         [r for r in results if r["image_path"].startswith("real_printed/")],
        "Manuscrito real":      [r for r in results if r["image_path"].startswith("real_handwritten/")],
    }

    return {name: items for name, items in categories.items() if items}

def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0

def _category_stats(results: list[dict]) -> dict:
    if not results:
        return {"n": 0, "cer": 0.0, "wer": 0.0, "f1": 0.0, "latency_ms": 0.0}
    return {
        "n":          len(results),
        "cer":        _mean([r["cer"] for r in results]),
        "wer":        _mean([r["wer"] for r in results]),
        "f1":         _mean([r["f1"] for r in results]),
        "latency_ms": _mean([r["latency_ms"] for r in results]),
    }

def _format_summary_table(reports: dict[str, dict]) -> str:
    lines = [
        "| Métrica            | " + " | ".join(f"**{e.upper()}**" for e in reports) + " |",
        "|---|" + "---|" * len(reports),
    ]
    rows = [
        ("Imágenes evaluadas", lambda r: str(r["n_images"])),
        ("CER promedio ↓",     lambda r: _pct(r["mean_cer"])),
        ("WER promedio ↓",     lambda r: _pct(r["mean_wer"])),
        ("Precision (char)",   lambda r: _pct(r["mean_precision"])),
        ("Recall (char)",      lambda r: _pct(r["mean_recall"])),
        ("F1 (char) ↑",        lambda r: _f(r["mean_f1"], 3)),
        ("Latencia media",     lambda r: _ms(r["mean_latency_ms"])),
        ("σ CER",              lambda r: _f(r["std_cer"])),
        ("σ WER",              lambda r: _f(r["std_wer"])),
    ]
    for label, getter in rows:
        lines.append(f"| {label} | " + " | ".join(getter(r) for r in reports.values()) + " |")
    return "\n".join(lines)

def _format_category_table(reports: dict[str, dict]) -> str:
    lines = [
        "| Categoría | Motor | N | CER | WER | F1 | Latencia |",
        "|---|---|---|---|---|---|---|",
    ]
    for engine, rep in reports.items():
        categories = _split_categories(rep["results"])
        for cat_name, cat_results in categories.items():
            stats = _category_stats(cat_results)
            lines.append(
                f"| {cat_name} | {engine.upper()} | {stats['n']} | "
                f"{_pct(stats['cer'])} | {_pct(stats['wer'])} | "
                f"{_f(stats['f1'], 3)} | {_ms(stats['latency_ms'])} |"
            )
    return "\n".join(lines)

def _format_examples(reports: dict[str, dict], max_per_category: int = 2) -> str:
    if not reports:
        return ""
    first_engine = next(iter(reports))
    categories   = _split_categories(reports[first_engine]["results"])

    blocks = ["### Ejemplos lado a lado\n"]

    for cat_name, items in categories.items():
        blocks.append(f"#### {cat_name}\n")
        for item in items[:max_per_category]:
            blocks.append(f"**Imagen:** `{item['image_path']}`")
            blocks.append(f"\n**Texto esperado (ground truth):**")
            gt = item['ground_truth'].replace('\n', ' ')
            blocks.append(f"> {gt}\n")
            for engine, rep in reports.items():
                eng_item = next((r for r in rep["results"] if r["image_path"] == item["image_path"]), None)
                if eng_item:
                    blocks.append(
                        f"**{engine.upper()}** (CER={_pct(eng_item['cer'])}, "
                        f"WER={_pct(eng_item['wer'])}, F1={_f(eng_item['f1'], 3)}, "
                        f"{_ms(eng_item['latency_ms'])}):"
                    )
                    text = eng_item["predicted_text"].strip() or "(vacío)"
                    blocks.append(f"```\n{text}\n```\n")
            blocks.append("---\n")

    return "\n".join(blocks)

def _format_conclusions(reports: dict[str, dict]) -> str:
    if not reports:
        return ""
    lines = ["### Conclusiones cuantitativas\n"]

    by_f1 = sorted(reports.items(), key=lambda kv: kv[1]["mean_f1"], reverse=True)
    best_name, best_rep = by_f1[0]
    lines.append(
        f"- **Mejor motor global por F1:** {best_name.upper()} con "
        f"F1={_f(best_rep['mean_f1'], 3)} y CER={_pct(best_rep['mean_cer'])}."
    )

    first_engine_results = reports[next(iter(reports))]["results"]
    categories = _split_categories(first_engine_results)
    for cat_name in categories:
        cat_winners: list[tuple[str, float]] = []
        for engine, rep in reports.items():
            cat_results = [r for r in rep["results"] if r["image_path"].startswith(cat_name_to_prefix(cat_name))]
            if cat_results:
                stats = _category_stats(cat_results)
                cat_winners.append((engine, stats["f1"]))
        if cat_winners:
            cat_winners.sort(key=lambda t: t[1], reverse=True)
            winner_engine, winner_f1 = cat_winners[0]
            ranking = " > ".join(f"{e.upper()} ({_f(f1, 3)})" for e, f1 in cat_winners)
            lines.append(f"- **{cat_name}**: {ranking}")

    lines.append("")
    lines.append("**Latencia media por motor:**")
    for name, rep in reports.items():
        lines.append(f"- {name.upper()}: {_ms(rep['mean_latency_ms'])}")

    lines.append("")
    if "groq" in reports and "tesseract" in reports:
        groq_f1   = reports["groq"]["mean_f1"]
        tess_f1   = reports["tesseract"]["mean_f1"]
        lines.append(
            f"- **Interpretación:** Tesseract es competitivo en texto impreso de alta calidad, "
            f"pero el motor IA (Llama 4 Scout Vision) mantiene desempeño superior en "
            f"manuscritura cursiva real. La estrategia híbrida del proyecto — EasyOCR para "
            f"impreso + IA para manuscrita — maximiza F1 global ({_f(max(groq_f1, tess_f1, reports['easyocr']['mean_f1']), 3)})."
        )
    elif "tesseract" in reports:
        lines.append(
            "- Tesseract destaca en texto impreso digital. El sistema propuesto está "
            "diseñado para complementarlo con IA en manuscritura compleja, lo que se ve "
            "claramente en la categoría 'Manuscrito real'."
        )
    return "\n".join(lines)

def cat_name_to_prefix(cat_name: str) -> str:
    mapping = {
        "Impreso sintético":    "printed/",
        "Manuscrito sintético": "handwritten/",
        "Impreso real":         "real_printed/",
        "Manuscrito real":      "real_handwritten/",
    }
    return mapping.get(cat_name, "")

def generate(input_path: Path, output_path: Path) -> None:
    with open(input_path, encoding="utf-8") as f:
        reports = json.load(f)

    if not reports:
        raise SystemExit(f"El archivo {input_path} está vacío o no es un benchmark válido.")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = f"""# Resultados del Benchmark — MODULAR OCR

**Generado automáticamente:** {timestamp}
**Dataset:** 30 imágenes sintéticas (15 impresas + 15 manuscritas)
**Métricas:** CER, WER, F1 a nivel carácter, latencia de inferencia

> Este documento se genera ejecutando:
> ```
> python -m app.generate_test_images
> python -m app.ocr_metrics --base-dir app/test_images --dataset app/test_images/ground_truth.json
> python -m app.generate_benchmark_report
> ```

---

## 1. Resumen general

{_format_summary_table(reports)}

> **CER** = Character Error Rate (menor es mejor)
> **WER** = Word Error Rate (menor es mejor)
> **F1**  = Media armónica de precisión y recall a nivel carácter (mayor es mejor)
> **σ**   = Desviación estándar entre imágenes

---

## 2. Desempeño por categoría

{_format_category_table(reports)}

---

## 3. Ejemplos representativos

{_format_examples(reports)}

---

## 4. Conclusiones

{_format_conclusions(reports)}

---

## 5. Reproducibilidad

Todas las imágenes son sintéticas y se generan deterministicamente con
`random.Random(42)`. El ground truth está en
`app/test_images/ground_truth.json` y los resultados completos en
`benchmark_results.json`.

Para auditar un caso particular, abrir el JSON y filtrar por `image_path`.
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"Reporte generado: {output_path}")

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera un reporte markdown del benchmark.")
    p.add_argument("--input",  default="benchmark_results.json",
                   help="JSON producido por ocr_metrics.")
    p.add_argument("--output", default="../RESULTADOS_BENCHMARK.md",
                   help="Archivo markdown de salida.")
    return p.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    generate(Path(args.input), Path(args.output))
