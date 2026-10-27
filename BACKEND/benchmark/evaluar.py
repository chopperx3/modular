"""Benchmark reproducible de motores OCR sobre escritura a mano.

Cada motor recibe exactamente los mismos bytes de imagen y se mide con las
mismas metricas (CER y WER a nivel corpus, ademas del promedio por imagen) y
el mismo cronometro (tiempo de pared por imagen, tras una corrida de
calentamiento que no se cuenta).

Motores:
  easyocr    -> app.ocr_engine._run_easyocr (mismo codigo que produccion)
  tesseract  -> Tesseract 5, --oem 3 --psm 6, idiomas spa+eng
  groq       -> app.ocr_engine._run_groq_vision (modelo de vision remoto, solo comparacion)
  trocr      -> app.trocr_engine.run_trocr (CRAFT + TrOCR local, motor de manuscrito)

Uso (desde BACKEND/):
  python -m benchmark.evaluar --dataset benchmark/datasets/iam_lineas --motores easyocr tesseract
  python -m benchmark.evaluar --dataset benchmark/datasets/es_manuscrito --motores groq
  python -m benchmark.evaluar --reporte
  python -m benchmark.evaluar --todo          (todo de una vez)

Los resultados por imagen se guardan en benchmark/resultados/<dataset>__<motor>.jsonl.
Si una corrida se interrumpe, al repetir el comando continua donde se quedo.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import re
import statistics
import time
import unicodedata
from io import BytesIO
from pathlib import Path

from jiwer import cer as jiwer_cer, wer as jiwer_wer
from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / "resultados"
TESS_CONFIG = "--oem 3 --psm 6"
TESS_LANG = "spa+eng"

def norm_estricta(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    return " ".join(t.split())

def norm_flexible(t: str) -> str:
    t = norm_estricta(t).lower()
    t = "".join(c if not unicodedata.category(c).startswith("P") else " " for c in t)
    return " ".join(t.split())

NORMALIZACIONES = {"estricta": norm_estricta, "flexible": norm_flexible}

def _cargar_motor(nombre: str):
    if nombre == "easyocr":
        from app.ocr_engine import _run_easyocr
        return lambda b: _run_easyocr(b, ["es", "en"])
    if nombre == "groq":
        from app.ocr_engine import _run_groq_vision
        return _run_groq_vision
    if nombre == "trocr":
        from app.trocr_engine import run_trocr
        return run_trocr
    if nombre == "tesseract":
        import os
        import pytesseract
        cmd = os.getenv("TESSERACT_CMD", "").strip()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

        def _tess(b: bytes) -> str:
            img = ImageOps.exif_transpose(Image.open(BytesIO(b))).convert("RGB")
            return pytesseract.image_to_string(img, lang=TESS_LANG, config=TESS_CONFIG).strip()
        return _tess
    raise ValueError(f"Motor desconocido: {nombre}")

def _version_motor(nombre: str) -> str:
    try:
        if nombre == "easyocr":
            import easyocr
            return f"easyocr {easyocr.__version__}"
        if nombre == "tesseract":
            import pytesseract
            return f"tesseract {pytesseract.get_tesseract_version()}"
        if nombre == "groq":
            from app.ocr_engine import GROQ_MODEL
            return GROQ_MODEL
        if nombre == "trocr":
            import transformers
            from app.trocr_engine import TROCR_BEAMS, TROCR_MODEL
            return f"{TROCR_MODEL} (beams={TROCR_BEAMS}, transformers {transformers.__version__})"
    except Exception:
        pass
    return "?"

def correr(dataset: Path, motor: str, pausa: float) -> None:
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    RESULTADOS.mkdir(exist_ok=True)
    salida = RESULTADOS / f"{dataset.name}__{motor}.jsonl"
    hechos = set()
    if salida.exists():
        for linea in salida.read_text(encoding="utf-8").splitlines():
            r = json.loads(linea)
            if r.get("error") is None:
                hechos.add(r["imagen"])
        lineas_ok = [l for l in salida.read_text(encoding="utf-8").splitlines()
                     if json.loads(l).get("error") is None]
        salida.write_text("".join(l + "\n" for l in lineas_ok), encoding="utf-8")

    fn = _cargar_motor(motor)
    pendientes = [e for e in manifest if e["imagen"] not in hechos]
    print(f"[{motor}] {dataset.name}: {len(pendientes)} pendientes de {len(manifest)}")
    if not pendientes:
        return

    meta = {
        "motor": motor,
        "version": _version_motor(motor),
        "equipo": f"{platform.system()} {platform.machine()} {platform.processor() or ''}".strip(),
        "python": platform.python_version(),
    }

    t0 = time.perf_counter()
    try:
        fn((dataset / pendientes[0]["imagen"]).read_bytes())
    except Exception as e:
        print(f"  calentamiento fallo: {e}")
    print(f"  calentamiento (carga de modelo): {time.perf_counter() - t0:.1f} s")

    with open(salida, "a", encoding="utf-8") as out:
        for i, e in enumerate(pendientes, 1):
            datos = (dataset / e["imagen"]).read_bytes()
            err = None
            t0 = time.perf_counter()
            try:
                pred = fn(datos)
            except Exception as ex:
                pred, err = "", str(ex)[:300]
            ms = (time.perf_counter() - t0) * 1000.0
            reg = {**e, **meta, "prediccion": pred, "latencia_ms": round(ms, 1), "error": err}
            if err is None:
                for k, f in NORMALIZACIONES.items():
                    ref, hyp = f(e["referencia"]), f(pred)
                    reg[f"cer_{k}"] = round(float(jiwer_cer(ref, hyp)), 4)
                    reg[f"wer_{k}"] = round(float(jiwer_wer(ref, hyp)), 4)
            out.write(json.dumps(reg, ensure_ascii=False) + "\n")
            out.flush()
            estado = f"CER={reg.get('cer_flexible', float('nan')):.3f}" if err is None else f"ERROR {err[:80]}"
            print(f"  [{i}/{len(pendientes)}] {estado} {ms:.0f} ms {e['imagen']}")
            if pausa:
                time.sleep(pausa)

def _corpus(regs: list[dict], norm, metrica) -> float:
    refs = [norm(r["referencia"]) for r in regs]
    hyps = [norm(r["prediccion"]) for r in regs]
    return float(metrica(refs, hyps))

def _ic95(regs: list[dict], norm, metrica, n: int = 1000) -> tuple[float, float]:
    rng = random.Random(42)
    vals = []
    for _ in range(n):
        muestra = [regs[rng.randrange(len(regs))] for _ in regs]
        vals.append(_corpus(muestra, norm, metrica))
    vals.sort()
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]

def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"

def reporte() -> str:
    grupos: dict[tuple[str, str], list[dict]] = {}
    for p in sorted(RESULTADOS.glob("*.jsonl")):
        ds, motor = p.stem.split("__")
        regs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        regs = [r for r in regs if r.get("error") is None]
        if regs:
            grupos[(ds, motor)] = regs

    md = []
    for ds in sorted({d for d, _ in grupos}):
        md.append(f"### {ds}\n")
        md.append("| Motor | N | CER corpus (IC 95%) | WER corpus (IC 95%) | CER estricto | WER estricto | CER medio por imagen | Tiempo medio | Mediana | p95 |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for (d, motor), regs in sorted(grupos.items()):
            if d != ds:
                continue
            nf, ne = norm_flexible, norm_estricta
            cer_f = _corpus(regs, nf, jiwer_cer)
            wer_f = _corpus(regs, nf, jiwer_wer)
            cer_lo, cer_hi = _ic95(regs, nf, jiwer_cer)
            wer_lo, wer_hi = _ic95(regs, nf, jiwer_wer)
            lat = sorted(r["latencia_ms"] for r in regs)
            p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
            md.append(
                f"| {motor} | {len(regs)} | {_pct(cer_f)} ({_pct(cer_lo)}–{_pct(cer_hi)}) "
                f"| {_pct(wer_f)} ({_pct(wer_lo)}–{_pct(wer_hi)}) "
                f"| {_pct(_corpus(regs, ne, jiwer_cer))} | {_pct(_corpus(regs, ne, jiwer_wer))} "
                f"| {_pct(statistics.mean(r['cer_flexible'] for r in regs))} "
                f"| {statistics.mean(lat):.0f} ms | {statistics.median(lat):.0f} ms | {p95:.0f} ms |"
            )
        conds = sorted({r.get("condicion", "") for (d, _), rs in grupos.items() if d == ds for r in rs})
        if len(conds) > 1:
            md.append("\nPor condicion de captura (CER corpus, normalizacion flexible):\n")
            md.append("| Motor | " + " | ".join(conds) + " |")
            md.append("|---|" + "---|" * len(conds))
            for (d, motor), regs in sorted(grupos.items()):
                if d != ds:
                    continue
                celdas = []
                for c in conds:
                    sub = [r for r in regs if r.get("condicion", "") == c]
                    celdas.append(f"{_pct(_corpus(sub, norm_flexible, jiwer_cer))} (n={len(sub)})" if sub else "—")
                md.append(f"| {motor} | " + " | ".join(celdas) + " |")
        md.append("")
        versiones = sorted({(m, r["version"], r["equipo"]) for (d, m), rs in grupos.items() if d == ds for r in rs[:1]})
        for m, v, eq in versiones:
            md.append(f"- {m}: `{v}` en {eq}")
        md.append("")
    return "\n".join(md)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path)
    ap.add_argument("--motores", nargs="+", choices=["easyocr", "tesseract", "groq", "trocr"], default=[])
    ap.add_argument("--pausa-groq", type=float, default=2.5,
                    help="segundos entre peticiones a Groq (limite gratuito ~30 por minuto)")
    ap.add_argument("--reporte", action="store_true")
    ap.add_argument("--todo", action="store_true",
                    help="corre todos los datasets de benchmark/datasets con los tres motores y genera el reporte")
    args = ap.parse_args()

    if args.todo:
        motores = args.motores or ["easyocr", "tesseract", "trocr"]
        for ds in sorted(p for p in (BASE / "datasets").iterdir() if (p / "manifest.json").exists()):
            for m in motores:
                correr(ds, m, args.pausa_groq if m == "groq" else 0.0)
        args.reporte = True
    else:
        for m in args.motores:
            correr(args.dataset, m, args.pausa_groq if m == "groq" else 0.0)
    if args.reporte:
        texto = reporte()
        (RESULTADOS / "resumen.md").write_text(texto, encoding="utf-8")
        print(texto)

if __name__ == "__main__":
    main()
