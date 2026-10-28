"""Genera renglones manuscritos sintéticos en español para afinar TrOCR.

Cada renglón es texto en español (obras de dominio público) dibujado con una
tipografía de estilo manuscrito y degradado como una foto de celular:
inclinación de la letra, rotación, ondulación del renglón, grosor del trazo,
color de tinta, papel rayado, sombras, ruido, desenfoque y compresión JPEG.

Uso (desde BACKEND/):
    python -m entrenamiento.generar_sintetico --n 6000
    python -m entrenamiento.generar_sintetico --n 200 --salida entrenamiento/datos/prueba

Salida: <salida>/img/*.jpg y <salida>/manifest.json con el mismo formato que
benchmark/datasets (imagen, referencia, ...) más el campo "split" (train/val).

Fuentes de texto (dominio público en México: autores fallecidos hace más de 100 años):
    Cervantes, "Don Quijote" (Project Gutenberg #2000)
    Pérez Galdós, "Marianela" (#17340) y "Doña Perfecta" (#15725)
Tipografías: Google Fonts (licencias OFL / Apache), descargadas a entrenamiento/fuentes/.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import re
import unicodedata
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).resolve().parent
FUENTES_DIR = BASE / "fuentes"
CORPUS_DIR = BASE / "corpus"
SALIDA = BASE / "datos" / "sintetico_es"

LIBROS = {
    "quijote": 2000,
    "marianela": 17340,
    "dona_perfecta": 15725,
}

# Tipografías de Google Fonts con aspecto manuscrito (molde y cursiva).
TIPOGRAFIAS = [
    "Caveat", "Indie Flower", "Shadows Into Light", "Patrick Hand", "Kalam",
    "Gloria Hallelujah", "Homemade Apple", "Dancing Script", "Covered By Your Grace",
    "Reenie Beanie", "Architects Daughter", "Nothing You Could Do", "Just Another Hand",
    "Sue Ellen Francisco", "Gochi Hand", "Handlee", "Coming Soon", "Cedarville Cursive",
    "La Belle Aurore", "Over the Rainbow", "Waiting for the Sunrise", "Loved by the King",
    "Annie Use Your Telescope", "Schoolbell", "Zeyada", "Sacramento", "Nanum Pen Script",
    "Neucha", "Short Stack", "Mali", "Itim", "Delius", "Satisfy", "Yellowtail",
    "Kristi", "Dawning of a New Day", "Allura", "Courgette", "Merienda",
    "Swanky and Moo Moo", "Square Peg", "Edu SA Beginner", "Playpen Sans",
]

CARACTERES_ES = "áéíóúüñÁÉÍÓÚÜÑ¿¡"
ALFABETO = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    " .,;:¿?¡!()-\"'$%/" + CARACTERES_ES
)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# ── Descargas (una sola vez) ─────────────────────────────────────────────

def _descargar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "modular-ocr/2.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def asegurar_tipografias() -> list[Path]:
    FUENTES_DIR.mkdir(parents=True, exist_ok=True)
    rutas = []
    for familia in TIPOGRAFIAS:
        destino = FUENTES_DIR / (familia.replace(" ", "") + ".ttf")
        if not destino.exists():
            try:
                css = _descargar("https://fonts.googleapis.com/css2?family="
                                 + familia.replace(" ", "+")).decode()
                url = re.search(r"url\((https://[^)]+\.ttf)\)", css).group(1)
                destino.write_bytes(_descargar(url))
                print(f"  tipografía descargada: {familia}")
            except Exception as e:
                print(f"  no se pudo descargar {familia}: {e}")
                continue
        rutas.append(destino)
    return rutas

def soporta_espanol(ruta: Path) -> bool:
    """La tipografía debe tener todos los acentos, ñ y signos de apertura."""
    from fontTools.ttLib import TTFont
    try:
        cmap = TTFont(ruta).getBestCmap()
    except Exception:
        return False
    return all(ord(c) in cmap for c in CARACTERES_ES + "aeiouAEIOU0123456789")

def asegurar_corpus() -> str:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    textos = []
    for nombre, num in LIBROS.items():
        destino = CORPUS_DIR / f"{nombre}.txt"
        if not destino.exists():
            raw = _descargar(f"https://www.gutenberg.org/cache/epub/{num}/pg{num}.txt").decode("utf-8")
            destino.write_text(raw, encoding="utf-8")
            print(f"  texto descargado: {nombre}")
        raw = destino.read_text(encoding="utf-8")
        ini = raw.find("*** START OF")
        fin = raw.find("*** END OF")
        cuerpo = raw[raw.find("\n", ini) + 1: fin if fin > 0 else None]
        textos.append(cuerpo)
    return "\n".join(textos)

# ── Texto de cada renglón ────────────────────────────────────────────────

def _limpiar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFC", texto)
    # Las rayas de diálogo casi no aparecen en apuntes a mano; se quitan.
    texto = texto.replace("—", " ").replace("«", '"').replace("»", '"').replace("_", "")
    texto = texto.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    palabras = texto.split()
    return [p for p in palabras
            if all(c in ALFABETO for c in p)
            and any(c.isalnum() for c in p)          # sin signos sueltos ("-", ".")
            and (len(p) == 1 or not p.isupper())]   # sin títulos en mayúsculas

def _ngramas(palabras: list[str], n: int = 4) -> set[tuple[str, ...]]:
    norm = [re.sub(r"[^\wáéíóúüñ]", "", p.lower()) for p in palabras]
    return {tuple(norm[i:i + n]) for i in range(len(norm) - n + 1)}

def textos_excluidos() -> set[tuple[str, ...]]:
    """4-gramas de las hojas de prueba: ningún renglón de entrenamiento los repite."""
    from benchmark.preparar_manuscritas import HOJAS, MUESTRA_REPO
    excl: set[tuple[str, ...]] = set()
    for frases in HOJAS.values():
        for f in frases:
            excl |= _ngramas(f.split())
    excl |= _ngramas(MUESTRA_REPO[1].split())
    return excl

def _frase_numerica(rng: random.Random) -> str:
    opciones = [
        lambda: f"{rng.randint(1, 28)} de {rng.choice(MESES)} de {rng.randint(1990, 2030)}",
        lambda: f"Pagué ${rng.randint(10, 9999)} el día {rng.randint(1, 31)}",
        lambda: f"Mi número es {rng.randint(10**7, 10**9)}",
        lambda: f"{rng.randint(1, 12)}:{rng.randint(0, 59):02d} p.m. en el salón {rng.randint(1, 40)}",
        lambda: f"Tarea {rng.randint(1, 20)}: páginas {rng.randint(1, 150)} a {rng.randint(151, 300)}",
        lambda: f"{rng.randint(2, 99)} alumnos, {rng.randint(1, 9)} grupos y {rng.randint(10, 99)}%",
    ]
    return rng.choice(opciones)()

def generar_textos(palabras: list[str], n: int, rng: random.Random,
                   excluidos: set[tuple[str, ...]]) -> list[str]:
    textos = []
    intentos = 0
    while len(textos) < n and intentos < n * 20:
        intentos += 1
        if rng.random() < 0.06:
            textos.append(_frase_numerica(rng))
            continue
        largo = rng.randint(3, 9)
        i = rng.randrange(0, len(palabras) - largo)
        frase = palabras[i:i + largo]
        texto = " ".join(frase)
        if not 12 <= len(texto) <= 64 or _ngramas(frase) & excluidos:
            continue
        if max(sum(c.isalnum() for c in p) for p in frase) < 4:   # restos como "i sob. m sob."
            continue
        r = rng.random()
        if r < 0.08:
            texto = texto.capitalize()
        elif r < 0.10:
            texto = texto.lower()
        textos.append(texto)
    return textos

# ── Dibujo y degradación ────────────────────────────────────────────────

def _dibujar(texto: str, fuente: Path, rng: random.Random) -> np.ndarray:
    """Devuelve la máscara de tinta (0..1) del renglón, palabra por palabra."""
    size = rng.randint(34, 58)
    font = ImageFont.truetype(str(fuente), size)
    palabras = texto.split(" ")
    espacio = font.getlength(" ") * rng.uniform(0.8, 1.6)
    ancho = int(sum(font.getlength(p) for p in palabras) + espacio * len(palabras) + size * 2)
    alto = int(size * 3)
    img = Image.new("L", (ancho, alto), 0)
    d = ImageDraw.Draw(img)
    x = size * 0.6
    base = alto * 0.6
    deriva = rng.uniform(-0.04, 0.04)     # el renglón sube o baja poco a poco
    for p in palabras:
        y = base + deriva * x + rng.gauss(0, size * 0.04)
        d.text((x, y), p, font=font, fill=255, anchor="ls")
        x += font.getlength(p) + espacio * rng.uniform(0.7, 1.3)
    bbox = img.getbbox()
    if bbox is None:
        raise ValueError("renglón vacío")
    m = 8
    img = img.crop((max(0, bbox[0] - m), max(0, bbox[1] - m),
                    min(img.width, bbox[2] + m), min(img.height, bbox[3] + m)))
    return np.asarray(img, dtype=np.float32) / 255.0

def _deformar(mask: np.ndarray, rng: random.Random) -> np.ndarray:
    import cv2

    h, w = mask.shape
    # Inclinación de la letra (shear) y pequeña rotación.
    shear = rng.uniform(-0.35, 0.25)
    ang = math.radians(rng.uniform(-2.0, 2.0))
    pad = int(abs(shear) * h) + 10
    ty = 10 + max(0.0, -math.sin(ang) * w)
    M = np.array([[math.cos(ang), -math.sin(ang) + shear, pad],
                  [math.sin(ang), math.cos(ang), ty]], dtype=np.float32)
    out = cv2.warpAffine(mask, M, (w + 2 * pad, h + 20 + int(abs(math.sin(ang)) * w)),
                         flags=cv2.INTER_LINEAR, borderValue=0)
    # Ondulación vertical suave del renglón.
    if rng.random() < 0.6:
        hh, ww = out.shape
        amp = rng.uniform(0.5, 3.0)
        per = rng.uniform(150, 600)
        fase = rng.uniform(0, 2 * math.pi)
        xs, ys = np.meshgrid(np.arange(ww, dtype=np.float32), np.arange(hh, dtype=np.float32))
        ys = ys + amp * np.sin(xs / per * 2 * math.pi + fase)
        out = cv2.remap(out, xs, ys, cv2.INTER_LINEAR, borderValue=0)
    # Grosor del trazo (pluma fina o plumón).
    r = rng.random()
    k = np.ones((2, 2), np.uint8)
    if r < 0.25:
        out = cv2.dilate(out, k, iterations=1)
    elif r < 0.40:
        out = cv2.erode(out, k, iterations=1)
    ys, xs = np.nonzero(out > 0.1)
    if len(xs) == 0:
        raise ValueError("renglón vacío tras deformar")
    m = rng.randint(6, 24)
    y0, y1 = max(0, ys.min() - m), min(out.shape[0], ys.max() + m)
    x0, x1 = max(0, xs.min() - m), min(out.shape[1], xs.max() + m)
    return out[y0:y1, x0:x1]

def _papel(h: int, w: int, rng: random.Random) -> np.ndarray:
    # Papel blanco a crema: mismo brillo en los tres canales, con un tono cálido leve.
    b = rng.uniform(215, 255)
    base = np.array([b, b - rng.uniform(0, 8), b - rng.uniform(0, 22)], np.float32)
    papel = np.ones((h, w, 3), np.float32) * base
    # Sombra o luz desigual (foto con celular).
    if rng.random() < 0.6:
        gx = np.linspace(rng.uniform(-1, 1), rng.uniform(-1, 1), w)[None, :, None]
        gy = np.linspace(rng.uniform(-1, 1), rng.uniform(-1, 1), h)[:, None, None]
        papel *= 1 - rng.uniform(0.05, 0.35) * np.clip((gx + gy + 2) / 4, 0, 1)
    # Renglón de cuaderno y margen.
    if rng.random() < 0.45:
        color = np.array([rng.uniform(120, 180), rng.uniform(160, 200), rng.uniform(200, 240)], np.float32)
        y = int(h * rng.uniform(0.72, 0.92))
        papel[y:y + rng.randint(1, 2)] = color
    if rng.random() < 0.05:
        x = int(w * rng.uniform(0.0, 0.08))
        papel[:, x:x + 2] = np.array([220, 120, 120], np.float32)
    return papel

def degradar(mask: np.ndarray, rng: random.Random) -> Image.Image:
    h, w = mask.shape
    papel = _papel(h, w, rng)
    tintas = [(20, 20, 25), (25, 35, 110), (15, 30, 80), (60, 60, 60), (40, 40, 50)]
    tinta = np.array(rng.choice(tintas), np.float32) + np.array([rng.uniform(-10, 10) for _ in range(3)])
    alpha = np.clip(mask * rng.uniform(0.75, 1.0), 0, 1)[..., None]
    img = papel * (1 - alpha) + tinta * alpha
    img += np.random.default_rng(rng.randint(0, 2**31)).normal(0, rng.uniform(0, 8), img.shape)
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if rng.random() < 0.5:
        out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.2)))
    if rng.random() < 0.3:   # resolución baja
        f = rng.uniform(0.45, 0.8)
        small = out.resize((max(8, int(out.width * f)), max(8, int(out.height * f))), Image.BILINEAR)
        out = small.resize(out.size, Image.BILINEAR)
    return out

def renglon(texto: str, fuente: Path, rng: random.Random) -> Image.Image:
    return degradar(_deformar(_dibujar(texto, fuente, rng), rng), rng)

# ── Programa ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=6000, help="número de renglones")
    ap.add_argument("--val", type=float, default=0.05, help="fracción para validación")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--semilla", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.semilla)
    print("Preparando tipografías y textos...")
    fuentes = [f for f in asegurar_tipografias() if soporta_espanol(f)]
    print(f"  {len(fuentes)} tipografías con acentos, ñ y ¿¡")
    # Validación con tipografías que el entrenamiento no ve: mide si el modelo
    # generaliza a otra letra, no si memorizó una tipografía.
    rng.shuffle(fuentes)
    n_val_f = max(2, len(fuentes) // 8)
    fuentes_val, fuentes_train = fuentes[:n_val_f], fuentes[n_val_f:]
    palabras = _limpiar(asegurar_corpus())
    print(f"  corpus: {len(palabras):,} palabras")

    textos = generar_textos(palabras, args.n, rng, textos_excluidos())
    img_dir = args.salida / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    n_val = int(len(textos) * args.val)
    for i, texto in enumerate(textos):
        split = "val" if i < n_val else "train"
        fuente = rng.choice(fuentes_val if split == "val" else fuentes_train)
        try:
            img = renglon(texto, fuente, rng)
        except Exception as e:
            print(f"  omitido ({fuente.stem}): {e}")
            continue
        nombre = f"img/s{i:06d}.jpg"
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=rng.randint(55, 95))
        (args.salida / nombre).write_bytes(buf.getvalue())
        manifest.append({"imagen": nombre, "referencia": texto, "subconjunto": "sintetico_es",
                         "idioma": "es", "condicion": "sintetico", "split": split,
                         "fuente": fuente.stem})
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(textos)}")

    (args.salida / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    n_tr = sum(1 for m in manifest if m["split"] == "train")
    print(f"Listo: {len(manifest)} renglones ({n_tr} train / {len(manifest) - n_tr} val) en {args.salida}")
    print(f"Tipografías de validación (no vistas al entrenar): {', '.join(f.stem for f in fuentes_val)}")

if __name__ == "__main__":
    main()
