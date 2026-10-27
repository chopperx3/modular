# MODULAR OCR — Sistema OCR Inteligente para Documentos Manuscritos

> Proyecto modular CUCEI — Universidad de Guadalajara
> Eduardo Israel Ramírez Baltazar · Mtra. Martha del Carmen Gutiérrez Salmerón

Sistema distribuido para digitalización de documentos manuscritos e impresos.
El manuscrito se reconoce localmente con CRAFT + TrOCR (Transformer
codificador-decodificador) y el impreso con EasyOCR, en nodos worker repartidos
en varias computadoras, con comparación cuantitativa frente a Tesseract.

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
| [`PROTOCOLO_WEBSOCKET.md`](PROTOCOLO_WEBSOCKET.md) | Canal WebSocket entre dispositivos: mensajes, concurrencia, desconexiones y demo |
| [`MODELO_TROCR.md`](MODELO_TROCR.md) | Modelo de IA para manuscrito: segmentación CRAFT, TrOCR, modelo matemático y resultados |
| [`CLUSTER_DISTRIBUIDO.md`](CLUSTER_DISTRIBUIDO.md) | Coordinador y workers en varias computadoras: protocolo TCP, reparto de carga y tolerancia a fallos |

## Quickstart

```bash
# Backend
cd BACKEND
py -3.11 -m venv .venv && .venv\Scripts\activate    # Python 3.11 (torch/transformers)
pip install -r requirements.txt
copy .env.example .env       # HANDWRITING_ENGINE=trocr (local) por defecto
uvicorn app.main:app --host 0.0.0.0 --port 8000   # 0.0.0.0 para que otros dispositivos se conecten

# Workers de OCR (en cada computadora de la red, con la IP del coordinador)
python -m app.worker --coordinator 192.168.1.10:9000 --id laptop-1

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
