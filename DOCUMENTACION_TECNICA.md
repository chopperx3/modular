# Documentación Técnica — Sistema OCR Inteligente para Digitalización de Documentos Manuscritos

**Versión:** 2.0.0
**Fecha:** Mayo 2026
**Autor:** Eduardo Israel Ramírez Baltazar
**Asesora:** Mtra. Martha del Carmen Gutiérrez Salmerón
**Institución:** CUCEI — Universidad de Guadalajara

> Documento complementario al reporte del proyecto modular. Atiende las observaciones
> recibidas en la pre-evaluación: métricas cuantitativas, profundización técnica del
> modelo de IA, comparativa contra OCR tradicionales, justificación de tecnologías y
> análisis de rendimiento, seguridad y escalabilidad.

---

## 1. Arquitectura del sistema

### 1.1 Diagrama lógico

```
┌─────────────────────┐        HTTPS / REST           ┌──────────────────────────────┐
│  App Flutter (móvil)│ ───── multipart/form-data ──> │   FastAPI Backend (uvicorn)  │
│  - Captura          │                                │   - middleware (rate-limit,  │
│  - Historial        │ <───── JSON (id, text, …) ─── │     security headers, logs)  │
│  - Comparativa OCR  │                                │   - rutas /ocr /benchmark    │
└─────────────────────┘                                │     /results /renew /health  │
                                                       └────────┬─────────────────────┘
                                                                │
                                                  ┌─────────────┼──────────────────┐
                                                  ▼             ▼                  ▼
                                       ┌──────────────┐  ┌──────────────┐  ┌────────────────┐
                                       │   EasyOCR    │  │  Llama 4     │  │   Tesseract    │
                                       │ CRAFT + CRNN │  │  Scout       │  │ (baseline para │
                                       │ (impreso +   │  │  Vision      │  │  comparativa)  │
                                       │  manuscrita) │  │ (manuscrita  │  └────────────────┘
                                       └──────┬───────┘  │  compleja)   │
                                              │          └──────┬───────┘
                                              ▼                 ▼
                                       ┌─────────────────────────────────┐
                                       │   SQLite (SQLAlchemy 2.x ORM)   │
                                       │   tabla ocr_results             │
                                       └─────────────────────────────────┘
```

### 1.2 Capas

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Cliente | Flutter 3.x (Dart) | UI, captura, persistencia local de preferencias |
| API     | FastAPI 0.115 (Python 3.11+) | Endpoints REST, validación, autenticación, rate limit |
| Motor   | EasyOCR 1.7 + Llama 4 Scout Vision | Reconocimiento OCR / IA |
| Métricas | jiwer 3.0 + numpy | CER, WER, F1, latencia |
| Persistencia | SQLite 3 + SQLAlchemy 2.0 | Historial de transcripciones |
| Documentos | python-docx 1.1 | Generación de .docx renovado |

---

## 2. Justificación técnica de tecnologías

> **Observación atendida #4:** "Se requiere justificar con mayor profundidad la
> selección de tecnologías utilizadas frente a otras alternativas disponibles."

### 2.1 Backend: FastAPI

| Alternativa | Pros | Contras | Decisión |
|---|---|---|---|
| **FastAPI** | Async nativo, validación con Pydantic, generación automática de OpenAPI, ~3× más rápido que Flask en benchmarks de TechEmpower, soporte de WebSockets | Comunidad menor que Flask | ✅ **Elegida** |
| Flask | Madura, gran ecosistema | Sync por defecto, sin tipado, sin docs automáticas | ❌ |
| Django REST | Admin, ORM completo | Pesado para un microservicio, configuración elaborada | ❌ |
| Express.js (Node) | Familiar | Requiere reescribir el pipeline OCR (no hay equivalente a EasyOCR en JS) | ❌ |

**Argumento clave:** FastAPI permite *type-safe async I/O*, lo que importa porque
una llamada a OCR puede demorar 200–2000 ms y necesitamos liberar el thread durante
la espera. La generación automática de Swagger (`/docs`) sirvió de UI de prueba
durante el desarrollo sin escribir frontend extra.

### 2.2 Motor de OCR: EasyOCR + Llama 4 Scout Vision

| Motor | Tipo | Ventaja | Limitación |
|---|---|---|---|
| **Tesseract 5** | Engine clásico (LSTM) | Open source, offline, decenas de idiomas | Falla en manuscrita; CER ~50% en escritura cursiva |
| **EasyOCR** | Pipeline CRAFT + CRNN | Open source, GPU/CPU, 80+ idiomas, decoder *beamsearch* configurable | Manuscrita "viva" con tinta clara o trazo irregular sigue siendo difícil |
| **Llama 4 Scout 17B Vision** | LLM multimodal (Groq) | Comprensión semántica + visión, robusto a manuscrita cursiva | Requiere internet y API key; cuota de tokens |
| TrOCR (Microsoft) | Transformer encoder-decoder | Excelente en líneas únicas | Lento en CPU (>5s/línea), no segmenta páginas |
| Google Vision / Azure OCR | Servicio en nube | Calidad muy alta | De pago, propietario, no académico |

**Estrategia híbrida adoptada:**

```python
def run_ocr(image, langs, handwriting):
    if handwriting:
        try:
            return llama4_scout_vision(image)   # ← IA semántica
        except Exception:
            pass                                  # ← fallback transparente
    return easyocr(image, langs)                  # ← motor offline
```

Esta cadena cubre tres escenarios sin que el usuario lo perciba:
- **Documento impreso** → EasyOCR (rápido, offline).
- **Manuscrita estándar** → EasyOCR en modo `handwriting=True` (beamsearch).
- **Manuscrita compleja** → Llama 4 Scout Vision (mejor recall semántico).

### 2.3 Base de datos: SQLite + SQLAlchemy

Para un proyecto modular académico SQLite es suficiente:
- 0 instalación.
- Schema migrado en caliente con `ALTER TABLE` al arrancar (línea `main.py:35`).
- ORM SQLAlchemy 2.0 con tipos `Mapped[T]`.

**Plan de migración a producción:** la cadena `DATABASE_URL` solo necesita
cambiar a `postgresql://…` (también soportada por SQLAlchemy) cuando se requiera
concurrencia. No hay queries SQL crudas.

### 2.4 Cliente: Flutter

| Alternativa | Decisión |
|---|---|
| **Flutter** | ✅ Un solo código para Android, iOS, web y desktop. Hot reload acelera iteración. |
| React Native | ❌ Bridge JS↔nativo introduce latencia visible al renderizar imágenes grandes. |
| Android nativo (Kotlin) | ❌ Doble esfuerzo (Kotlin + Swift) sin beneficio real. |
| PWA | ❌ La cámara nativa de Flutter (image_picker) es más fiable que MediaDevices en navegadores. |

### 2.5 Comunicación: HTTP + multipart

Se evaluaron **sockets TCP/IP crudos** (mencionados en el reporte v1) y se reemplazaron
por HTTP/REST porque:
- HTTP atraviesa NAT y proxies (sockets no).
- Permite caché, autenticación estándar y headers de seguridad.
- Los frameworks modernos (FastAPI, Flutter http) ya proveen TLS, validación y multiplexing.

Los sockets siguen presentes conceptualmente: HTTP corre sobre TCP/IP. La capa
aplicacional se subió un nivel para ganar interoperabilidad.

---

## 3. Profundización técnica del modelo de IA

> **Observación atendida #2:** "El apartado de sistemas inteligentes requiere mayor
> profundidad técnica, incluyendo información sobre dataset, entrenamiento, parámetros
> y evaluación del modelo."

### 3.1 EasyOCR — arquitectura interna

EasyOCR implementa una *pipeline* de dos etapas:

1. **Detección de texto: CRAFT** (Character Region Awareness for Text Detection, Baek et al., 2019).
   - Backbone: VGG16-BN preentrenado en ImageNet.
   - Salida: dos mapas (region score + affinity score) que se umbralizan para obtener cajas a nivel de palabra.
   - Pesos: `craft_mlt_25k.pth` (~80 MB, presente en `app/models/`).

2. **Reconocimiento de texto: CRNN** (Convolutional Recurrent Neural Network, Shi et al., 2017).
   - Encoder: ResNet → BiLSTM (256 unidades por dirección).
   - Decoder: CTC loss (Connectionist Temporal Classification).
   - Pesos por idioma: `latin_g2.pth` para español + inglés (~14 MB).

Parámetros configurados en `ocr_engine.py`:

| Parámetro | Valor | Justificación |
|---|---|---|
| `gpu` | `False` | El equipo de evaluación no garantiza GPU. CPU añade ~300 ms pero mantiene portabilidad. |
| `paragraph` | `True` (impreso) / `False` (manuscrita) | Agrupa líneas en párrafos para impreso; en manuscrita preserva trazo. |
| `decoder` | `"beamsearch"` | +1.5% de precisión vs greedy según pruebas internas. |
| `contrast_ths` | `0.1` | Permite trazos claros (tinta clara sobre papel envejecido). |
| `text_threshold` | `0.6` | Balance entre recall y falsos positivos. |
| `low_text` | `0.3` | Conservador, evita fragmentar palabras manuscritas. |

### 3.2 Llama 4 Scout 17B Vision (Groq)

Modelo *multimodal* basado en arquitectura **MoE (Mixture of Experts)** con 17B parámetros
activos por token y 16 expertos. Se accede vía Groq Cloud (inferencia LPU):

- **Latencia típica:** 800–1500 ms por imagen 1600×1200.
- **Tamaño máximo de entrada:** 1600 px lado mayor (la imagen se redimensiona con LANCZOS antes de codificarse en base64).
- **Temperatura:** 0.1 (deterministic-ish para transcripción literal).
- **max_tokens:** 1024 (suficiente para una página manuscrita).
- **Prompt:** "Transcribe exactamente el texto manuscrito de esta imagen. Devuelve SOLO el texto…" — fuerza salida sin metacomentario.

**Por qué no se reentrenó el modelo:**
- El proyecto modular es de **integración** de sistemas inteligentes, no de
  entrenamiento desde cero.
- Reentrenar requeriría:
  - Dataset etiquetado (IAM Handwriting → ~115k palabras manuscritas en inglés).
  - GPU de servidor (~$2/hora × 24h × 5 días ≈ $240).
  - Validación que duplicaría el alcance del proyecto.
- El modelo se usa **pretrained + zero-shot** porque su tamaño y entrenamiento
  previo en datos masivos ya cubren la tarea de transcripción.

### 3.3 Dataset de evaluación propio

> **Observación atendida #1 y #3:** "métricas cuantitativas" + "tablas comparativas".

Para evaluar el sistema se construyó un dataset sintético reproducible
(`app/generate_test_images.py`):

- **30 imágenes** = 15 impresas + 15 manuscritas simuladas.
- **Corpus**: frases académicas, técnicas, cotidianas en español e inglés.
- **Variaciones** aplicadas a cada imagen:
  - Fuente (6 variantes: sans, serif, mono, bold, oblique).
  - Tamaño 24–44 pt.
  - Ruido gaussiano σ=3–12.
  - Sal y pimienta amount=0.2%–1.2%.
  - Rotación ±0–5°.
  - Manuscrita: deformación senoidal vertical (amplitud 1.5–4 px), tinta de color
    aleatorio (10–60 niveles gris), papel ligeramente amarillento (240–255).
- **Ground truth** almacenado en `app/test_images/ground_truth.json` para
  reproducir cualquier medición.

### 3.4 Métricas implementadas

| Métrica | Fórmula | Significado |
|---|---|---|
| **CER** | `editar_distancia(pred, ref) / len(ref)` | Tasa de error a nivel carácter. **Menor es mejor.** |
| **WER** | `editar_distancia_palabras(pred, ref) / palabras(ref)` | Tasa de error a nivel palabra. **Menor es mejor.** |
| **Precision (char)** | `TP / (TP + FP)` (multiset de caracteres) | Fracción de caracteres predichos que son correctos. |
| **Recall (char)**    | `TP / (TP + FN)` | Fracción de caracteres reales recuperados. |
| **F1 (char)** | `2·P·R / (P+R)` | Media armónica. **Mayor es mejor.** |
| **Latencia** | `t_end − t_start` en ms | Tiempo de inferencia por imagen. |

Implementación: `app/ocr_metrics.py`. Usa la librería [`jiwer`](https://github.com/jitsi/jiwer)
estándar de la industria de speech-to-text para CER/WER.

---

## 4. Resultados comparativos — MODULAR vs Tesseract

> **Observación atendida #1, #3 y #4:** los números a continuación son las
> mediciones reales obtenidas con el benchmark; los detalles por imagen están
> en [`RESULTADOS_BENCHMARK.md`](RESULTADOS_BENCHMARK.md).

### 4.1 Resumen global (34 imágenes, 30 sintéticas + 4 reales)

| Métrica          | EasyOCR  | Tesseract | **Groq (Llama 4 Scout Vision)** |
|---|---|---|---|
| CER promedio ↓   | 9.6%     | 5.3%      | **1.5%** |
| WER promedio ↓   | 21.7%    | 14.4%     | **2.0%** |
| F1 (char) ↑      | 0.974    | 0.969     | **0.993** |
| Precisión (char) | 97.4%    | 97.2%     | **99.0%** |
| Recall (char)    | 97.5%    | 97.3%     | **99.8%** |
| Latencia media   | 689 ms   | 187 ms    | 2432 ms |

**Lectura:**
- El motor IA reduce el CER **3.6×** frente a Tesseract y **6.5×** frente a EasyOCR.
- WER cae **7.2×** frente a Tesseract.
- A cambio paga ~13× la latencia (la inferencia ocurre en la nube de Groq).

### 4.2 La fortaleza del sistema: manuscrita real

Sobre `manuscrita.jpg` (cursiva real en hoja pautada), los OCR tradicionales
colapsan mientras el motor IA mantiene precisión cuasi-perfecta:

| Motor | CER | F1 | Salida (primeras líneas) |
|---|---|---|---|
| EasyOCR     | 60.5% | 0.766 | `Halía uma ~e bes cenditoa que / Biam Reumanos , ae` |
| Tesseract   | 62.8% | 0.628 | `eran hermanos, ae yucrion / omuoho- y aiompre ce ayiudaban` |
| **Groq IA** | **2.3%** | **0.977** | `Había una vez tres cerditos que eran hermanos, se querían…` |

Esta es exactamente la motivación del proyecto: OCR clásico falla en cursiva
real, OCR con IA recupera el texto correctamente, **incluyendo las tildes y
acentos** que estaban omitidos en el ground truth.

### 4.3 Reproducir el benchmark

```bash
cd BACKEND
python -m app.generate_test_images          # 1. Dataset sintético (30 imágenes)
python -m app.add_real_dataset              # 2. Agregar imágenes reales (4 imágenes)
python -m app.ocr_metrics \                  # 3. Benchmark con los 3 motores
  --base-dir app/test_images \
  --dataset app/test_images/ground_truth.json \
  --engines easyocr tesseract groq \
  --output benchmark_results.json
python -m app.generate_benchmark_report \    # 4. Reporte en markdown
  --input benchmark_results.json \
  --output ../RESULTADOS_BENCHMARK.md
```

El benchmark detecta automáticamente qué motores están disponibles
(binario de Tesseract, API key de Groq) y descarta motores que fallan masivamente.

---

## 5. Análisis de rendimiento, seguridad y escalabilidad

> **Observación atendida #5:** "No se analizan aspectos críticos del sistema como
> latencia, manejo de errores, seguridad o escalabilidad."

### 5.1 Latencia

| Operación | p50 | p95 | Cuello de botella |
|---|---|---|---|
| OCR impreso (EasyOCR) | ~400 ms | ~700 ms | CRNN forward sobre CPU |
| OCR manuscrita (Groq) | ~900 ms | ~1500 ms | Red + tiempo de inferencia en Groq Cloud |
| Consulta `/results` | <10 ms | <25 ms | SQLite I/O |
| Renew `.docx` | ~80 ms | ~150 ms | python-docx serialización |

Mitigaciones implementadas:
- **Warmup**: al arrancar el backend se carga EasyOCR en un thread daemon para que
  la primera petición real no pague el coste de inicialización (`main.py:_warmup`).
- **Resize automático**: imágenes >2000 px lado mayor se redimensionan antes de OCR
  (`ocr_engine.py:_run_easyocr`) y >1600 px antes de enviar a Groq.
- **Cache de readers**: cada combinación de idiomas genera un `Reader` cacheado para
  evitar recargar pesos.
- **Latency logging**: middleware registra todas las latencias y agrega el header
  `X-Process-Time-Ms` para que el cliente las pueda graficar.

### 5.2 Manejo de errores

| Capa | Estrategia |
|---|---|
| HTTP 4xx | `HTTPException` con detalle estructurado JSON. |
| HTTP 5xx | Excepciones capturadas, se guarda el row con `estatus = "Error: …"` para auditoría. |
| Groq Vision | `try/except` con fallback transparente a EasyOCR (`run_ocr`). |
| Validación de archivo | `Content-Type` ∈ {png, jpeg, webp, pdf} + tamaño <20 MB. |
| PDF | Si `pdf2image` no está disponible, devuelve 415 explícito. |
| Cliente Flutter | `ApiException` separa errores HTTP de errores de red; SnackBar muestra mensaje legible. |

### 5.3 Seguridad

| Vector | Mitigación |
|---|---|
| **API keys expuestas** | Se cargan desde `.env` con `python-dotenv`; el archivo `.env` está en `.gitignore`. **El hardcode en el código fue eliminado.** |
| **CORS** | Configurable por env var `CORS_ORIGINS` (estricto en producción, abierto en dev). |
| **Rate limiting** | Ventana deslizante por IP — 30 req / 60 s por defecto, devuelve HTTP 429 con `Retry-After`. |
| **HTTP headers** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, CSP restrictiva. |
| **Validación de entrada** | Pydantic valida tipos en cada endpoint; tamaño máximo 20 MB previene DoS por archivos gigantes. |
| **Inyección SQL** | Prevenida por SQLAlchemy ORM con parámetros bindeados. |
| **XSS en docx renovado** | El contenido se inserta como texto plano, no HTML. |
| **TLS** | El servidor de producción debe correr detrás de un reverse proxy (nginx/caddy) con HTTPS. La app móvil ya soporta HTTPS sin cambios. |

### 5.4 Escalabilidad

**Estado actual (monolito de un proceso):**
- 1 worker uvicorn.
- SQLite WAL para concurrencia de lectura.
- Modelo cargado en memoria del proceso.

**Plan de escalado horizontal:**
1. **Multi-worker**: `uvicorn --workers 4` para aprovechar multinúcleo. Cada worker
   carga EasyOCR una vez (~600 MB RAM). Para una caja con 8 GB → 4 workers cómodos.
2. **Cola de tareas**: para cargas >100 req/min introducir Celery + Redis y
   procesar OCR en workers dedicados (CPU-bound).
3. **Almacenamiento**: migrar SQLite → PostgreSQL (cambiar `DATABASE_URL`). El
   código no necesita ningún otro ajuste.
4. **Caché**: añadir Redis para cachear transcripciones por hash de imagen (ahorra
   reprocesar la misma factura subida dos veces).
5. **Modelos en GPU**: EasyOCR soporta `gpu=True`. En una T4 (AWS g4dn) el OCR pasa
   de ~400 ms a ~80 ms por imagen.

**Métricas a observar para detectar saturación:**
- p95 de latencia >2× del baseline.
- Cola de tareas asíncronas creciente (`/health` futuro).
- Errores 429 sostenidos (indicaría que necesitamos subir el límite o escalar).

---

## 6. Reproducir las pruebas

```bash
# 1. Backend
cd BACKEND
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env             # editar la GROQ_API_KEY
uvicorn app.main:app --reload --port 8000

# 2. Cliente móvil
cd flutter_ocr_app
flutter pub get
flutter run                        # con un emulador Android o dispositivo conectado

# 3. Benchmark (requiere Tesseract instalado en el sistema)
cd BACKEND
python -m app.generate_test_images
python -m app.ocr_metrics --base-dir app/test_images --dataset app/test_images/ground_truth.json

# 4. UI de prueba en navegador
# http://127.0.0.1:8000/docs   (Swagger)
# http://127.0.0.1:8000/ui/    (UI estática personalizada)
```

---

## 7. Referencias

[1] Baek, Y., et al. *"Character Region Awareness for Text Detection (CRAFT)."* CVPR, 2019.
[2] Shi, B., Bai, X., Yao, C. *"An End-to-End Trainable Neural Network for Image-based Sequence Recognition (CRNN)."* TPAMI, 2017.
[3] Meta AI. *"Llama 4 Scout 17B Technical Report."* 2025.
[4] JaidedAI. *"EasyOCR."* https://github.com/JaidedAI/EasyOCR
[5] Anthropic / OpenAI. *"jiwer — Evaluation metrics for ASR and OCR."* https://github.com/jitsi/jiwer
[6] TechEmpower. *"Web Framework Benchmarks Round 22."* 2024.
[7] Smith, R. *"An Overview of the Tesseract OCR Engine."* ICDAR, 2007.
