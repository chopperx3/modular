from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT_ROOT     = Path(__file__).resolve().parent.parent.parent
TEST_IMAGES_DIR  = Path(__file__).resolve().parent / "test_images"
GROUND_TRUTH     = TEST_IMAGES_DIR / "ground_truth.json"

REAL_SAMPLES = [
    (
        PROJECT_ROOT / "manuscrita.jpg",
        "real_handwritten",
        (
            "Habia una vez tres cerditos que\n"
            "eran hermanos, se querian\n"
            "mucho y siempre se ayudaban entre\n"
            "si para protegerse de los peligros..."
        ),
    ),
    (
        PROJECT_ROOT / "R.png",
        "real_printed",
        (
            "No me rendi.\n"
            "No, me rendi.\n"
            "Con o sin coma?\n"
            "Tu eliges."
        ),
    ),
    (
        PROJECT_ROOT / "ejemplo.jpg",
        "real_printed",
        (
            "EJEMPLO:\n"
            '"Los volcanes y los terremotos son dos procesos geologicos '
            "que alteran la forma de la tierra por erosion. Los volcanes "
            "estan formados por chimeneas o fisuras en la corteza "
            "terrestre, a traves de las cuales es expulsado el magma, "
            "a diferencia de los terremotos que son movimientos producidos "
            "en la corteza terrestre. Por otra parte, los volcanes son "
            "producidos por la elevada temperatura que existe en el "
            "interior de la Tierra, en cambio, los terremotos son causados "
            'por la ruptura de rocas de la corteza terrestre".'
        ),
    ),
    (
        PROJECT_ROOT / "Frase-parar-imprimir-en-tarjeta-724x1024.png",
        "real_printed",
        (
            "NO DEJES DE BRILLAR\n"
            "SOLO PORQUE A ALGUNOS LES MOLESTE LA LUZ\n"
            "BUDDHA"
        ),
    ),
]

def main() -> None:
    if not GROUND_TRUTH.exists():
        raise SystemExit(
            f"No existe {GROUND_TRUTH}. Corre primero:\n"
            f"  python -m app.generate_test_images"
        )

    with open(GROUND_TRUTH, encoding="utf-8") as f:
        gt: dict[str, str] = json.load(f)

    added = 0
    for src, subdir, text in REAL_SAMPLES:
        if not src.exists():
            print(f"  [!] No encontrado: {src} - se omite")
            continue
        dst_dir = TEST_IMAGES_DIR / subdir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        rel = f"{subdir}/{src.name}"
        gt[rel] = text
        added += 1
        print(f"  [+] {rel}  ({len(text)} chars)")

    with open(GROUND_TRUTH, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)

    print(f"\nGround truth actualizado: {len(gt)} entradas ({added} reales).")

if __name__ == "__main__":
    main()
