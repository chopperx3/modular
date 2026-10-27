import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.trocr_engine import group_lines  # noqa: E402

def test_agrupa_palabras_en_renglones_de_arriba_a_abajo():
    boxes = [
        (300, 112, 420, 150),   # renglón 2, palabra derecha
        (10, 10, 120, 50),      # renglón 1
        (140, 14, 260, 48),     # renglón 1
        (12, 110, 280, 148),    # renglón 2
        (20, 210, 200, 250),    # renglón 3
    ]
    assert group_lines(boxes) == [(10, 10, 260, 50), (12, 110, 420, 150), (20, 210, 200, 250)]

def test_letras_altas_no_unen_renglones_vecinos():
    # Una palabra con mayúscula/ascendentes que apenas toca el renglón de arriba.
    boxes = [(10, 10, 200, 50), (10, 45, 120, 95), (130, 60, 300, 95)]
    assert len(group_lines(boxes)) == 2

_IAM = BACKEND / "benchmark" / "datasets" / "iam_lineas" / "img" / "a01-058x-06.png"

@pytest.mark.skipif(not _IAM.exists(), reason="imágenes de IAM no disponibles (licencia, no se versionan)")
def test_trocr_lee_una_linea_de_iam():
    pytest.importorskip("transformers")
    pytest.importorskip("easyocr")
    from jiwer import cer

    from app.trocr_engine import run_page

    text, lines = run_page(_IAM.read_bytes())
    assert len(lines) == 1
    assert cer("government would try to get germany to", text.lower().replace(".", "")) < 0.15
