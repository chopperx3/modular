# MODULAR OCR — Sistema OCR Inteligente para Documentos Manuscritos

> Proyecto modular CUCEI — Universidad de Guadalajara
> Eduardo Israel Ramírez Baltazar · Mtra. Martha del Carmen Gutiérrez Salmerón

Sistema distribuido para digitalización de documentos manuscritos e impresos
mediante OCR clásico (EasyOCR) combinado con un modelo de visión por
inteligencia artificial (Llama 4 Scout 17B) y comparado cuantitativamente
frente a Tesseract.

---

## Componentes

| Carpeta | Descripción |
|---|---|
| [`BACKEND/`](BACKEND) | API REST en FastAPI con OCR, métricas y benchmark |
| [`flutter_ocr_app/`](flutter_ocr_app) | App móvil Flutter (Material 3) |

## Documentación

| Documento | Contenido |
|---|---|
| [`DOCUMENTACION_TECNICA.md`](DOCUMENTACION_TECNICA.md) | Justificación de tecnologías, modelo IA, seguridad, escalabilidad |
| [`RESULTADOS_BENCHMARK.md`](RESULTADOS_BENCHMARK.md) | Tablas y ejemplos de CER / WER / F1 |
| [`BACKEND/README.md`](BACKEND/README.md) | Cómo arrancar el servidor y endpoints |

## Quickstart

```bash
# Backend
cd BACKEND
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env       # editar GROQ_API_KEY
uvicorn app.main:app --reload --port 8000

# App móvil (en otra terminal)
cd flutter_ocr_app
flutter pub get
flutter run
```

## Atendido en esta versión (v2.0)

Respecto a las observaciones de la pre-evaluación:

- ✅ **Métricas cuantitativas:** módulo `ocr_metrics.py` con CER, WER, F1, latencia.
- ✅ **Profundización del modelo IA:** documento técnico con arquitectura,
  parámetros, dataset y justificación de modelo pretrained vs entrenamiento.
- ✅ **Comparativa contra OCR tradicionales:** benchmark EasyOCR vs Tesseract,
  reporte automático con tablas y ejemplos.
- ✅ **Evidencia de pruebas:** dataset reproducible de 30 imágenes con ground
  truth, métricas guardadas en JSON, tablas en markdown.
- ✅ **Justificación técnica de tecnologías:** sección 2 del documento técnico
  compara cada elección frente a alternativas.
- ✅ **Análisis de rendimiento, seguridad y escalabilidad:** sección 5 del
  documento técnico con plan de escalado horizontal y mitigaciones de seguridad.
- ✅ **Seguridad:** API keys movidas a `.env`, rate limiting, security headers, CORS, validación de entrada.
- ✅ **Interfaz móvil rediseñada:** navegación por pestañas, historial, vista de comparativa OCR en vivo.

## Repositorio

https://github.com/chopperx3/modular  ·  Versión: v2.0.0  ·  Licencia: MIT
