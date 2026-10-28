import random
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from entrenamiento import generar_sintetico as gs  # noqa: E402

def test_limpieza_quita_signos_sueltos_y_titulos():
    palabras = gs._limpiar("CAPÍTULO I —dijo don Quijote—. ¿Qué tal? «Bien» señor - y")
    assert "CAPÍTULO" not in palabras and "-" not in palabras
    assert "¿Qué" in palabras and '"Bien"' in palabras and "señor" in palabras

def test_no_repite_frases_de_las_hojas_de_prueba():
    excluidos = gs.textos_excluidos()
    palabras = ("había una vez la reunión será el jueves a las cinco de la tarde "
                "y luego otra frase cualquiera para el texto de relleno").split() * 50
    textos = gs.generar_textos(palabras, 200, random.Random(1), excluidos)
    assert textos
    assert not any("será el jueves a las" in t.lower() for t in textos)

@pytest.mark.skipif(not any(gs.FUENTES_DIR.glob("*.ttf")) if gs.FUENTES_DIR.exists() else True,
                    reason="tipografías no descargadas")
def test_dibuja_un_renglon_con_acentos():
    fuente = next(f for f in sorted(gs.FUENTES_DIR.glob("*.ttf")) if gs.soporta_espanol(f))
    img = gs.renglon("¿Mañana entregarás la tarea?", fuente, random.Random(3))
    assert img.mode == "RGB"
    assert img.width > 3 * img.height > 0
