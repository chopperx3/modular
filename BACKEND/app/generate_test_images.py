
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

THIS_DIR   = Path(__file__).resolve().parent
OUTPUT_DIR = THIS_DIR / "test_images"
PRINTED_DIR     = OUTPUT_DIR / "printed"
HANDWRITTEN_DIR = OUTPUT_DIR / "handwritten"

def _resolve_font_paths() -> dict[str, str]:
    import platform
    candidates: dict[str, list[str]] = {
        "sans":       ["C:/Windows/Fonts/arial.ttf",   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       "/Library/Fonts/Arial.ttf"],
        "sans_bold":  ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  "/Library/Fonts/Arial Bold.ttf"],
        "serif":      ["C:/Windows/Fonts/times.ttf",   "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",      "/Library/Fonts/Times New Roman.ttf"],
        "serif_bold": ["C:/Windows/Fonts/timesbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/Library/Fonts/Times New Roman Bold.ttf"],
        "mono":       ["C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",   "/Library/Fonts/Courier New.ttf"],
        "oblique":    ["C:/Windows/Fonts/ariali.ttf",  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf","/Library/Fonts/Arial Italic.ttf"],
    }
    resolved: dict[str, str] = {}
    for name, paths in candidates.items():
        for p in paths:
            if Path(p).exists():
                resolved[name] = p
                break
    return resolved

FONT_PATHS = _resolve_font_paths()

SAMPLES = [

    "El aprendizaje automatico permite a las computadoras aprender de datos.",
    "La precision del sistema OCR fue evaluada con imagenes reales.",
    "Ingenieria en Computacion - Universidad de Guadalajara",
    "Fecha de entrega: 21 de mayo de 2026",
    "Calificacion final: 95 puntos sobre 100",

    "FastAPI version 0.115.5 con Python 3.11",
    "POST /ocr/ HTTP/1.1 Content-Type: multipart/form-data",
    "WER = 0.08  CER = 0.03  Precision = 97.2%",

    "Comprar: leche, pan, aguacate y tomate",
    "Llamar al doctor el lunes a las 10 am",
    "Mi numero de control es 220345678",
    "Tarea: leer capitulos 3 y 4 del libro",

    "EasyOCR vs Tesseract: comparativa de rendimiento",
    "Reconocimiento optico de caracteres manuscritos",
    "Sistema distribuido: app movil + backend + base de datos",
]

def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_PATHS.get(name)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    for p in FONT_PATHS.values():
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _add_gaussian_noise(img: Image.Image, sigma: float = 8.0) -> Image.Image:
    arr   = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, sigma, arr.shape)
    arr   = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)

def _add_salt_pepper(img: Image.Image, amount: float = 0.01) -> Image.Image:
    arr  = np.array(img)
    mask = np.random.random(arr.shape[:2])
    arr[mask < amount / 2]       = 0
    arr[mask > 1 - amount / 2]   = 255
    return Image.fromarray(arr)

def _rotate_slight(img: Image.Image, max_angle: float = 3.0) -> Image.Image:
    angle = random.uniform(-max_angle, max_angle)
    return img.rotate(angle, expand=False, fillcolor=255)

def make_printed_image(
    text: str,
    font_name: str = "sans",
    font_size: int = 32,
    noise_sigma: float = 5.0,
    salt_pepper: float = 0.005,
    slight_rotation: float = 1.5,
    width: int = 800,
) -> Image.Image:
    font    = _load_font(font_name, font_size)
    padding = 40

    dummy = Image.new("RGB", (1, 1))
    draw  = ImageDraw.Draw(dummy)
    bbox  = draw.textbbox((0, 0), text, font=font)
    tw    = bbox[2] - bbox[0]
    th    = bbox[3] - bbox[1]

    W = max(width, tw + padding * 2)
    H = th + padding * 2

    img  = Image.new("L", (W, H), color=255)
    draw = ImageDraw.Draw(img)
    x    = (W - tw) // 2
    y    = padding
    draw.text((x, y), text, font=font, fill=0)

    img = _add_gaussian_noise(img, sigma=noise_sigma)
    img = _add_salt_pepper(img, amount=salt_pepper)
    img = _rotate_slight(img, max_angle=slight_rotation)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
    return img.convert("RGB")

def make_handwritten_image(
    text: str,
    font_size: int = 36,
    width: int = 800,
) -> Image.Image:
    font    = _load_font("oblique", font_size)
    padding = 50

    dummy = Image.new("RGB", (1, 1))
    draw  = ImageDraw.Draw(dummy)
    bbox  = draw.textbbox((0, 0), text, font=font)
    tw    = bbox[2] - bbox[0]
    th    = bbox[3] - bbox[1]

    W  = max(width, tw + padding * 2)
    H  = th + padding * 2 + 30

    base_color = random.randint(240, 255)
    img  = Image.new("L", (W, H), color=base_color)
    draw = ImageDraw.Draw(img)

    ink = random.randint(10, 60)
    draw.text((padding, padding), text, font=font, fill=ink)

    arr = np.array(img, dtype=np.float32)
    amplitude = random.uniform(1.5, 4.0)
    frequency = random.uniform(0.008, 0.015)
    shifted   = np.ones_like(arr) * base_color
    for x in range(arr.shape[1]):
        dy = int(amplitude * math.sin(2 * math.pi * frequency * x))
        if dy >= 0:
            shifted[dy:, x] = arr[:arr.shape[0] - dy, x]
        else:
            shifted[:arr.shape[0] + dy, x] = arr[-dy:, x]
    arr = shifted

    noise = np.random.normal(0, random.uniform(10, 20), arr.shape)
    arr   = np.clip(arr + noise, 0, 255).astype(np.uint8)
    img   = Image.fromarray(arr)

    img = _rotate_slight(img, max_angle=random.uniform(2, 5))
    img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.0)))

    return img.convert("RGB")

def generate_all() -> dict[str, str]:
    for d in [PRINTED_DIR, HANDWRITTEN_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    ground_truth: dict[str, str] = {}
    rng = random.Random(42)

    font_names  = list(FONT_PATHS.keys())
    font_sizes  = [24, 28, 32, 36, 42]

    print(f"Generando {len(SAMPLES)} imágenes impresas...")
    for i, text in enumerate(SAMPLES):
        fname = f"printed_{i:02d}.jpg"
        fpath = PRINTED_DIR / fname
        fn    = rng.choice(font_names)
        fs    = rng.choice(font_sizes)
        ns    = rng.uniform(3, 12)
        sp    = rng.uniform(0.002, 0.012)
        rot   = rng.uniform(0, 2)
        img   = make_printed_image(text, font_name=fn, font_size=fs,
                                   noise_sigma=ns, salt_pepper=sp,
                                   slight_rotation=rot)
        img.save(str(fpath), "JPEG", quality=92)
        ground_truth[f"printed/{fname}"] = text
        print(f"  [{i+1:02d}/{len(SAMPLES)}] {fname}  font={fn} size={fs}")

    print(f"\nGenerando {len(SAMPLES)} imágenes manuscritas simuladas...")
    for i, text in enumerate(SAMPLES):
        fname = f"handwritten_{i:02d}.jpg"
        fpath = HANDWRITTEN_DIR / fname
        fs    = rng.choice([32, 36, 40, 44])
        img   = make_handwritten_image(text, font_size=fs)
        img.save(str(fpath), "JPEG", quality=90)
        ground_truth[f"handwritten/{fname}"] = text
        print(f"  [{i+1:02d}/{len(SAMPLES)}] {fname}  size={fs}")

    gt_path = OUTPUT_DIR / "ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, ensure_ascii=False, indent=2)
    print(f"\nGround truth guardado en: {gt_path}")
    print(f"Total imágenes: {len(ground_truth)}")
    return ground_truth

if __name__ == "__main__":
    generate_all()
