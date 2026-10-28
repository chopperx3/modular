"""Afina (fine-tuning) TrOCR con renglones manuscritos en español.

Parte del modelo inglés microsoft/trocr-base-handwritten y ajusta sus pesos
minimizando la entropía cruzada  L = -sum_t log P(y_t | y_<t, x)  sobre los
renglones de los conjuntos indicados (campo "split" de cada manifest.json).

En CPU conviene --congelar-codificador: el codificador visual (ViT) ya sabe
"ver" trazos; lo que falta es el idioma, que vive en el decodificador. Así cada
paso solo calcula gradientes del decodificador y es varias veces más rápido.
En una GPU (p. ej. Google Colab) se puede entrenar todo el modelo.

Uso (desde BACKEND/):
    python -m entrenamiento.afinar_trocr --datos entrenamiento/datos/sintetico_es \\
        --congelar-codificador --epocas 2 --lote 8
    python -m entrenamiento.afinar_trocr --datos entrenamiento/datos/sintetico_es \\
        --evaluar-solo                     (CER del modelo base, sin entrenar)

Resultado: el mejor modelo (menor CER de validación) en --salida, listo para
TROCR_MODEL=<ruta>, y el historial de pérdida y CER en historial.csv.

Cada evaluación guarda también el punto actual (ultimo/ + estado.json): si el
proceso se corta, --reanudar sigue desde ahí. Para detenerlo de forma ordenada,
crear un archivo vacío llamado DETENER dentro de --salida.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
import warnings
from pathlib import Path

import torch
from jiwer import cer as jiwer_cer
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from transformers.models.vision_encoder_decoder.modeling_vision_encoder_decoder import shift_tokens_right

BACKEND = Path(__file__).resolve().parent.parent
SALIDA = BACKEND / "app" / "models" / "trocr-es"
MODELO_BASE = "microsoft/trocr-base-handwritten"
MAX_TOKENS = 96

class Renglones(Dataset):

    def __init__(self, entradas: list[dict], processor):
        self.entradas = entradas
        self.processor = processor

    def __len__(self) -> int:
        return len(self.entradas)

    def __getitem__(self, i: int) -> dict:
        e = self.entradas[i]
        img = Image.open(e["_ruta"]).convert("RGB")
        pixel_values = self.processor(images=img, return_tensors="pt").pixel_values[0]
        tok = self.processor.tokenizer
        # Sin el <s> inicial: el modelo publicado arranca a generar con </s> y
        # luego escribe el texto directo ([2, t1, t2, ..., 2]).
        ids = tok(e["referencia"], max_length=MAX_TOKENS + 1, truncation=True,
                  padding="max_length").input_ids[1:]
        labels = torch.tensor([t if t != tok.pad_token_id else -100 for t in ids])
        return {"pixel_values": pixel_values, "labels": labels}

def perdida(model, pixel_values: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """Entropía cruzada media por token: L = -1/T sum_t log P(y_t | y_<t, x).

    Se calcula aquí y no con `labels=` de transformers porque en la versión 4.57
    esa ruta vuelve a desplazar las etiquetas y la pérdida sale desalineada.
    """
    dec_in = shift_tokens_right(labels, model.config.pad_token_id, model.config.decoder_start_token_id)
    logits = model(pixel_values=pixel_values, decoder_input_ids=dec_in).logits
    return torch.nn.functional.cross_entropy(
        logits.reshape(-1, logits.size(-1)), labels.reshape(-1), ignore_index=-100)

def cargar_entradas(dirs: list[Path], split: str) -> list[dict]:
    out = []
    for d in dirs:
        for e in json.loads((d / "manifest.json").read_text(encoding="utf-8")):
            if e.get("split", "train") == split:
                out.append({**e, "_ruta": str(d / e["imagen"])})
    return out

@torch.inference_mode()
def evaluar(model, processor, entradas: list[dict], lote: int, device) -> tuple[float, list[str]]:
    model.eval()
    preds = []
    for i in range(0, len(entradas), lote):
        imgs = [Image.open(e["_ruta"]).convert("RGB") for e in entradas[i:i + lote]]
        pv = processor(images=imgs, return_tensors="pt").pixel_values.to(device)
        ids = model.generate(pv, max_new_tokens=MAX_TOKENS)
        preds += [t.strip() for t in processor.batch_decode(ids, skip_special_tokens=True)]
    refs = [e["referencia"] for e in entradas]
    return float(jiwer_cer(refs, preds)), preds

class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()

def _duplicar_salida(ruta: Path) -> None:
    """Escribe la salida en pantalla y en un archivo que otros programas pueden leer mientras corre."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    f = open(ruta, "a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, f)
    sys.stderr = _Tee(sys.__stderr__, f)

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, nargs="+", required=True, help="carpetas con manifest.json")
    ap.add_argument("--modelo", default=MODELO_BASE, help="modelo de partida (HF o carpeta local)")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--epocas", type=float, default=2.0)
    ap.add_argument("--lote", type=int, default=8)
    ap.add_argument("--acumular", type=int, default=2, help="pasos de gradiente acumulados")
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--max-pasos", type=int, default=0, help="tope de pasos (0 = sin tope)")
    ap.add_argument("--eval-cada", type=int, default=200, help="evaluar cada N pasos de optimización")
    ap.add_argument("--guardar-cada", type=int, default=25,
                    help="guardar el punto actual cada N pasos para poder reanudar (0 = solo al evaluar)")
    ap.add_argument("--max-val", type=int, default=300, help="renglones de validación por evaluación")
    ap.add_argument("--congelar-codificador", action="store_true")
    ap.add_argument("--evaluar-solo", action="store_true")
    ap.add_argument("--reanudar", action="store_true",
                    help="seguir desde el último punto guardado en --salida (estado.json + ultimo/)")
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--log", type=Path, help="copiar también la salida a este archivo")
    args = ap.parse_args()
    if args.log:
        _duplicar_salida(args.log)

    from transformers import TrOCRProcessor, VisionEncoderDecoderModel, get_linear_schedule_with_warmup

    random.seed(args.semilla)
    torch.manual_seed(args.semilla)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    cache = str(BACKEND / "app" / "models" / "trocr")
    estado_path = args.salida / "estado.json"
    ultimo = args.salida / "ultimo"
    reanudar = args.reanudar and estado_path.exists() and ultimo.exists()
    processor = TrOCRProcessor.from_pretrained(args.modelo, cache_dir=cache)
    model = VisionEncoderDecoderModel.from_pretrained(str(ultimo) if reanudar else args.modelo,
                                                      cache_dir=cache).to(device)
    tok = processor.tokenizer
    model.config.decoder_start_token_id = model.generation_config.decoder_start_token_id
    model.config.pad_token_id = tok.pad_token_id
    model.config.eos_token_id = tok.sep_token_id

    train = cargar_entradas(args.datos, "train")
    val = cargar_entradas(args.datos, "val")
    random.shuffle(val)
    val = val[:args.max_val]
    print(f"Dispositivo: {device} | train: {len(train)} | val: {len(val)} | modelo: {args.modelo}")

    args.salida.mkdir(parents=True, exist_ok=True)
    hist_path = args.salida / "historial.csv"
    if reanudar:
        estado = json.loads(estado_path.read_text(encoding="utf-8"))
        paso0, mejor, cer_base = estado["paso"], estado["mejor"], estado["cer_base"]
        print(f"Reanudando desde el paso {paso0} (mejor CER {100 * mejor:.2f} %, base {100 * cer_base:.2f} %)")
    else:
        t0 = time.perf_counter()
        cer_base, preds = evaluar(model, processor, val, args.lote, device)
        print(f"CER de validación antes de entrenar: {100 * cer_base:.2f} % ({time.perf_counter() - t0:.0f} s)")
        for e, p in list(zip(val, preds))[:5]:
            print(f"   REF: {e['referencia']}\n   OCR: {p}")
        if args.evaluar_solo:
            return
        with open(hist_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["paso", "perdida_media", "cer_val", "segundos"])
            csv.writer(f).writerow([0, "", round(cer_base, 4), 0])
        paso0, mejor = 0, cer_base

    if args.congelar_codificador:
        for p in model.encoder.parameters():
            p.requires_grad = False
    entrenables = [p for p in model.parameters() if p.requires_grad]
    print(f"Parámetros entrenables: {sum(p.numel() for p in entrenables) / 1e6:.0f} M "
          f"de {sum(p.numel() for p in model.parameters()) / 1e6:.0f} M")

    torch.manual_seed(args.semilla + paso0)
    loader = DataLoader(Renglones(train, processor), batch_size=args.lote, shuffle=True,
                        num_workers=0, drop_last=True)
    pasos = math.ceil(len(loader) * args.epocas / args.acumular)
    if args.max_pasos:
        pasos = min(pasos, args.max_pasos)
    opt = torch.optim.AdamW(entrenables, lr=args.lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, num_warmup_steps=max(1, pasos // 20), num_training_steps=pasos)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(paso0):          # la tasa de aprendizaje sigue donde se quedó
            sched.step()

    def guardar_estado(paso: int) -> None:
        model.save_pretrained(ultimo)
        estado_path.write_text(json.dumps({"paso": paso, "mejor": mejor, "cer_base": cer_base,
                                           "pasos": pasos}), encoding="utf-8")

    detener = args.salida / "DETENER"
    if not reanudar:
        guardar_estado(0)       # al reanudar ya no repite la evaluación inicial
    paso = paso0
    acumulado, n_acum = 0.0, 0
    t_ini = time.perf_counter()
    model.train()
    if args.congelar_codificador:
        model.encoder.eval()
    terminado = paso >= pasos
    while not terminado:
        for lote in loader:
            pv = lote["pixel_values"].to(device)
            labels = lote["labels"].to(device)
            loss = perdida(model, pv, labels) / args.acumular
            loss.backward()
            acumulado += loss.item() * args.acumular
            n_acum += 1
            if n_acum % args.acumular:
                continue
            torch.nn.utils.clip_grad_norm_(entrenables, 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            paso += 1
            if paso % 10 == 0 or paso == paso0 + 1:
                transcurrido = time.perf_counter() - t_ini
                por_paso = transcurrido / (paso - paso0)
                print(f"paso {paso}/{pasos}  pérdida {acumulado / n_acum:.4f}  "
                      f"{por_paso:.1f} s/paso  faltan ~{por_paso * (pasos - paso) / 60:.0f} min", flush=True)
            if paso % args.eval_cada == 0 or paso == pasos:
                cer_val, _ = evaluar(model, processor, val, args.lote, device)
                model.train()
                if args.congelar_codificador:
                    model.encoder.eval()
                perdida_media = acumulado / n_acum
                with open(hist_path, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([paso, round(perdida_media, 4), round(cer_val, 4),
                                            round(time.perf_counter() - t_ini)])
                acumulado, n_acum = 0.0, 0
                marca = ""
                if cer_val < mejor:
                    mejor = cer_val
                    model.save_pretrained(args.salida)
                    processor.save_pretrained(args.salida)
                    marca = "  ← mejor, guardado"
                guardar_estado(paso)
                print(f"== paso {paso}: CER val {100 * cer_val:.2f} % (base {100 * cer_base:.2f} %){marca}",
                      flush=True)
            elif args.guardar_cada and paso % args.guardar_cada == 0:
                guardar_estado(paso)
                print(f"   punto guardado (paso {paso})", flush=True)
            if detener.exists():
                guardar_estado(paso)
                detener.unlink()
                print(f"Detenido a petición en el paso {paso}. Para seguir: --reanudar", flush=True)
                return
            if paso >= pasos:
                terminado = True
                break

    print(f"Listo. Mejor CER de validación: {100 * mejor:.2f} % (base {100 * cer_base:.2f} %)")
    if mejor < cer_base:
        print(f"Para usarlo: TROCR_MODEL={args.salida}")

if __name__ == "__main__":
    main()
