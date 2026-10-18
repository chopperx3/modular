"""Construye un subconjunto reproducible de lineas manuscritas de IAM.

Las lineas se reconstruyen pegando cada palabra recortada de IAM en su
posicion original dentro del formulario (bounding box de words.txt), por lo
que conservan la escritura real del autor. Solo se usan lineas cuya
segmentacion de todas sus palabras esta marcada como "ok".

Uso (desde BACKEND/):
    python -m benchmark.preparar_iam --iam-dir RUTA/IAM_Words --n 150
donde RUTA/IAM_Words contiene words.txt y la carpeta words/ descomprimida.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image

SEED = 42
OUT_DIR = Path(__file__).resolve().parent / "datasets" / "iam_lineas"

def _detokenize(tokens: list[str]) -> str:
    out = ""
    quote_open = False
    for tok in tokens:
        if not out:
            out = tok
            if tok == '"':
                quote_open = True
            continue
        if tok == '"':
            if quote_open:
                out += tok
            else:
                out += " " + tok
            quote_open = not quote_open
            continue
        if re.fullmatch(r"[.,;:!?)\]]+", tok) or tok.startswith("'") or out.endswith(("(", "[")):
            out += tok
        else:
            out += " " + tok
    out = re.sub(r'(^|\s)" (\S)', r'\1"\2', out)
    return out

def leer_words(iam_dir: Path) -> dict[str, list[dict]]:
    lineas: dict[str, list[dict]] = defaultdict(list)
    validas: dict[str, bool] = defaultdict(lambda: True)
    with open(iam_dir / "words.txt", encoding="utf-8") as f:
        for raw in f:
            if raw.startswith("#") or not raw.strip():
                continue
            parts = raw.rstrip("\n").split(" ")
            wid, seg = parts[0], parts[1]
            x, y, w, h = (int(v) for v in parts[3:7])
            texto = " ".join(parts[8:])
            line_id = "-".join(wid.split("-")[:3])
            if seg != "ok" or w <= 0 or h <= 0:
                validas[line_id] = False
            lineas[line_id].append({"id": wid, "x": x, "y": y, "w": w, "h": h, "texto": texto})
    return {k: v for k, v in lineas.items() if validas[k] and len(v) >= 4}

def _ruta_palabra(words_dir: Path, wid: str) -> Path:
    a, b = wid.split("-")[:2]
    return words_dir / a / f"{a}-{b}" / f"{wid}.png"

def reconstruir_linea(palabras: list[dict], words_dir: Path, margen: int = 20) -> Image.Image:
    x0 = min(p["x"] for p in palabras)
    y0 = min(p["y"] for p in palabras)
    x1 = max(p["x"] + p["w"] for p in palabras)
    y1 = max(p["y"] + p["h"] for p in palabras)
    canvas = Image.new("L", (x1 - x0 + 2 * margen, y1 - y0 + 2 * margen), 255)
    for p in palabras:
        img = Image.open(_ruta_palabra(words_dir, p["id"])).convert("L")
        canvas.paste(img, (p["x"] - x0 + margen, p["y"] - y0 + margen))
    return canvas

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iam-dir", required=True, type=Path)
    ap.add_argument("--n", type=int, default=150)
    args = ap.parse_args()

    lineas = leer_words(args.iam_dir)
    words_dir = args.iam_dir / "words"

    por_form: dict[str, list[str]] = defaultdict(list)
    for lid in sorted(lineas):
        por_form["-".join(lid.split("-")[:2])].append(lid)

    rng = random.Random(SEED)
    forms = sorted(por_form)
    rng.shuffle(forms)
    elegidas = []
    for form in forms[: args.n]:
        elegidas.append(rng.choice(por_form[form]))

    (OUT_DIR / "img").mkdir(parents=True, exist_ok=True)
    manifest = []
    for lid in sorted(elegidas):
        palabras = sorted(lineas[lid], key=lambda p: p["id"])
        if not all(_ruta_palabra(words_dir, p["id"]).exists() for p in palabras):
            continue
        img = reconstruir_linea(palabras, words_dir)
        rel = f"img/{lid}.png"
        img.save(OUT_DIR / rel)
        manifest.append({
            "imagen": rel,
            "referencia": _detokenize([p["texto"] for p in palabras]),
            "subconjunto": "iam_lineas",
            "idioma": "en",
            "condicion": "escaneo",
        })

    with open(OUT_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"{len(manifest)} lineas escritas en {OUT_DIR}")

if __name__ == "__main__":
    main()
