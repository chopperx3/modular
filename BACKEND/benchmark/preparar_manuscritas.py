"""Construye el conjunto de prueba manuscrito en espanol.

Cada foto corresponde a una hoja copiada a mano (ver HOJAS); su referencia es
el texto de esa hoja. Nombres esperados: escritorX_hojaY.jpg y, para fotos con
captura deficiente (poca luz, inclinada, sombra), escritorX_hojaY_dificil.jpg.

Las fotos se reducen a un lado mayor de 2000 px (JPEG calidad 90) y se corrige
la orientacion EXIF; es el mismo tope que aplica el backend antes de EasyOCR.

Uso (desde BACKEND/):
    python -m benchmark.preparar_manuscritas --fotos RUTA/A/LAS/FOTOS
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageOps

OUT_DIR = Path(__file__).resolve().parent / "datasets" / "es_manuscrito"
REPO = Path(__file__).resolve().parents[2]

HOJAS = {
    1: [
        "El sistema reconoce la escritura a mano.",
        "Mañana entregaré la tarea de matemáticas.",
        "La reunión será el jueves a las cinco.",
        "¿Dónde guardaste los documentos?",
        "Compré pan, leche y azúcar en la tienda.",
    ],
    2: [
        "El niño jugaba en el jardín con su perro.",
        "Guadalajara es una ciudad muy bonita.",
        "La biblioteca cierra a las ocho de la noche.",
        "¡Qué alegría verte después de tanto tiempo!",
        "El examen final tiene veinte preguntas.",
    ],
    3: [
        "Necesito enviar el informe antes del lunes.",
        "Mi número de cuenta es 214432892.",
        "La computadora procesa imágenes en segundos.",
        "Ayer llovió mucho y se inundó la calle.",
        "El maestro explicó la lección con paciencia.",
    ],
    4: [
        "Los alumnos presentaron su proyecto modular.",
        "Hay que revisar la ortografía del texto.",
        "El tren salió tarde por la lluvia.",
        "Escribe tu nombre completo en la hoja.",
        "La señora compró dos kilos de naranjas.",
    ],
}

MUESTRA_REPO = (
    "manuscrita.jpg",
    "Había una vez tres cerditos que\n"
    "eran hermanos, se querían\n"
    "mucho y siempre se ayudaban entre\n"
    "sí para protegerse de los peligros...",
)

PATRON = re.compile(r"escritor(\d+)_hoja(\d)(_dificil)?\.(jpe?g|png|heic|webp)$", re.IGNORECASE)

def _guardar(src: Path, dst: Path) -> None:
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    w, h = img.size
    if max(w, h) > 2000:
        r = 2000 / max(w, h)
        img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
    img.save(dst, format="JPEG", quality=90)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fotos", required=True, type=Path)
    args = ap.parse_args()

    (OUT_DIR / "img").mkdir(parents=True, exist_ok=True)
    manifest = []
    for src in sorted(args.fotos.iterdir()):
        m = PATRON.search(src.name)
        if not m:
            print(f"  [omitida] {src.name}")
            continue
        escritor, hoja, dificil = int(m.group(1)), int(m.group(2)), bool(m.group(3))
        rel = f"img/escritor{escritor}_hoja{hoja}{'_dificil' if dificil else ''}.jpg"
        _guardar(src, OUT_DIR / rel)
        manifest.append({
            "imagen": rel,
            "referencia": "\n".join(HOJAS[hoja]),
            "subconjunto": "es_manuscrito",
            "idioma": "es",
            "condicion": "dificil" if dificil else "normal",
            "escritor": escritor,
        })

    nombre, ref = MUESTRA_REPO
    if (REPO / nombre).exists():
        _guardar(REPO / nombre, OUT_DIR / f"img/{Path(nombre).stem}.jpg")
        manifest.append({
            "imagen": f"img/{Path(nombre).stem}.jpg",
            "referencia": ref,
            "subconjunto": "es_manuscrito",
            "idioma": "es",
            "condicion": "caligrafia",
            "escritor": 0,
        })

    with open(OUT_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"{len(manifest)} imagenes en {OUT_DIR}")

if __name__ == "__main__":
    main()
