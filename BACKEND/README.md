# MODULAR OCR — Backend (FastAPI)

Sistema OCR inteligente que combina **EasyOCR** + **Llama 4 Scout Vision** y se compara cuantitativamente contra **Tesseract**.

---

## 1. Instalación

```bash
cd BACKEND
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux / Mac

pip install -r requirements.txt

copy .env.example .env             # Windows
# cp .env.example .env             # Linux / Mac
# Editar .env y poner tu GROQ_API_KEY
```

### Instalar Tesseract (para la comparativa)

El benchmark compara contra **Tesseract 5** como baseline tradicional. Necesita
el binario nativo, no basta con `pip install`.

- **Windows**: instalar desde https://github.com/UB-Mannheim/tesseract/wiki
  (instalador `tesseract-ocr-w64-setup-*.exe`). Ajustar la ruta en `.env`:
  ```
  TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
  ```
  Para soporte en español, marcar el idioma `Spanish` durante la instalación.

- **Linux**: `sudo apt-get install tesseract-ocr tesseract-ocr-spa`
- **macOS**: `brew install tesseract tesseract-lang`

---

## 2. Arrancar el servidor

```bash
uvicorn app.main:app --reload --port 8000
```

Abrir:
- Swagger interactivo: http://127.0.0.1:8000/docs
- UI estática:        http://127.0.0.1:8000/ui/
- Health:             http://127.0.0.1:8000/health

---

## 3. Probar OCR rápido

1. POST `/ocr/` con una imagen multipart.
2. GET `/results` para listar.
3. GET `/results/{id}` para un detalle.

Parámetros de query:
- `lang=es,en` — idiomas (por defecto)
- `mode=handwriting` — activa el motor Llama 4 Scout Vision

---

## 4. Benchmark comparativo

```bash
# 1. Generar el dataset sintético (30 imágenes con ground truth)
python -m app.generate_test_images

# 2. Correr el benchmark (EasyOCR + Tesseract si está instalado)
python -m app.ocr_metrics \
    --base-dir app/test_images \
    --dataset app/test_images/ground_truth.json \
    --output benchmark_results.json

# 3. Generar el reporte markdown con tablas, ejemplos y conclusiones
python -m app.generate_benchmark_report \
    --input benchmark_results.json \
    --output ../RESULTADOS_BENCHMARK.md
```

El benchmark también puede correrse desde la app Flutter en la pestaña
"Comparar" — sube una imagen y opcionalmente pega el texto esperado para
obtener CER / WER / F1 en vivo.

---

## 5. Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `GROQ_API_KEY` | (vacío) | Clave de https://console.groq.com — sin ella, el modo manuscrita cae a EasyOCR |
| `GROQ_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Modelo Llama a usar |
| `TESSERACT_CMD` | (auto) | Ruta al binario Tesseract; solo necesario en Windows |
| `RATE_LIMIT_MAX` | `30` | Requests permitidas por IP en cada ventana |
| `RATE_LIMIT_WINDOW` | `60` | Tamaño de la ventana en segundos |
| `CORS_ORIGINS` | `*` | Origenes permitidos separados por coma |

---

## 6. Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Verifica disponibilidad de cada motor |
| `POST` | `/ocr/` | Procesa una imagen / PDF y guarda el resultado |
| `GET` | `/results` | Lista los resultados (paginado con `?limit=`) |
| `GET` | `/results/{id}` | Detalle de un resultado |
| `DELETE` | `/results/{id}` | Elimina un resultado |
| `POST` | `/renew/{id}` | Genera un `.docx` renovado a partir del texto |
| `POST` | `/benchmark/single` | Compara EasyOCR vs Tesseract en una imagen |
| `POST` | `/benchmark/run` | Lanza el benchmark completo en background |
| `GET` | `/benchmark/results` | Devuelve el JSON del último benchmark |

---

## 7. Documentación complementaria

- [`../DOCUMENTACION_TECNICA.md`](../DOCUMENTACION_TECNICA.md) — justificación de
  tecnologías, profundización del modelo IA, análisis de rendimiento /
  seguridad / escalabilidad.
- [`../RESULTADOS_BENCHMARK.md`](../RESULTADOS_BENCHMARK.md) — tablas y ejemplos
  comparativos generados automáticamente.
