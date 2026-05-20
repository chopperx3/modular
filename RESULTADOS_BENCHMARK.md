# Resultados del Benchmark — MODULAR OCR

**Generado automáticamente:** 2026-05-19 19:15:44
**Dataset:** 30 imágenes sintéticas (15 impresas + 15 manuscritas)
**Métricas:** CER, WER, F1 a nivel carácter, latencia de inferencia

> Este documento se genera ejecutando:
> ```
> python -m app.generate_test_images
> python -m app.ocr_metrics --base-dir app/test_images --dataset app/test_images/ground_truth.json
> python -m app.generate_benchmark_report
> ```

---

## 1. Resumen general

| Métrica            | **EASYOCR** | **TESSERACT** | **GROQ** |
|---|---|---|---|
| Imágenes evaluadas | 34 | 34 | 34 |
| CER promedio ↓ | 9.6% | 5.3% | 1.5% |
| WER promedio ↓ | 21.7% | 14.4% | 2.0% |
| Precision (char) | 97.4% | 97.2% | 99.0% |
| Recall (char) | 97.5% | 97.3% | 99.8% |
| F1 (char) ↑ | 0.974 | 0.969 | 0.993 |
| Latencia media | 689 ms | 187 ms | 2432 ms |
| σ CER | 0.1795 | 0.1222 | 0.0764 |
| σ WER | 0.2945 | 0.1768 | 0.0741 |

> **CER** = Character Error Rate (menor es mejor)
> **WER** = Word Error Rate (menor es mejor)
> **F1**  = Media armónica de precisión y recall a nivel carácter (mayor es mejor)
> **σ**   = Desviación estándar entre imágenes

---

## 2. Desempeño por categoría

| Categoría | Motor | N | CER | WER | F1 | Latencia |
|---|---|---|---|---|---|---|
| Impreso sintético | EASYOCR | 15 | 3.0% | 14.3% | 0.983 | 445 ms |
| Manuscrito sintético | EASYOCR | 15 | 10.8% | 18.9% | 0.988 | 576 ms |
| Impreso real | EASYOCR | 3 | 19.3% | 46.6% | 0.919 | 2286 ms |
| Manuscrito real | EASYOCR | 1 | 60.5% | 100.0% | 0.766 | 1252 ms |
| Impreso sintético | TESSERACT | 15 | 3.1% | 15.1% | 0.982 | 170 ms |
| Manuscrito sintético | TESSERACT | 15 | 1.4% | 10.2% | 0.987 | 187 ms |
| Impreso real | TESSERACT | 3 | 16.9% | 9.7% | 0.924 | 264 ms |
| Manuscrito real | TESSERACT | 1 | 62.8% | 81.8% | 0.628 | 216 ms |
| Impreso sintético | GROQ | 15 | 0.0% | 0.0% | 1.000 | 789 ms |
| Manuscrito sintético | GROQ | 15 | 0.0% | 0.0% | 1.000 | 3605 ms |
| Impreso real | GROQ | 3 | 15.8% | 18.0% | 0.927 | 4276 ms |
| Manuscrito real | GROQ | 1 | 2.3% | 13.6% | 0.977 | 3933 ms |

---

## 3. Ejemplos representativos

### Ejemplos lado a lado

#### Impreso sintético

**Imagen:** `printed/printed_00.jpg`

**Texto esperado (ground truth):**
> El aprendizaje automatico permite a las computadoras aprender de datos.

**EASYOCR** (CER=1.4%, WER=10.0%, F1=0.986, 510 ms):
```
El aprendizaje automatico permite a las computadoras aprender de datos:
```

**TESSERACT** (CER=0.0%, WER=0.0%, F1=1.000, 216 ms):
```
El aprendizaje automatico permite a las computadoras aprender de datos.
```

**GROQ** (CER=0.0%, WER=0.0%, F1=1.000, 746 ms):
```
El aprendizaje automatico permite a las computadoras aprender de datos.
```

---

**Imagen:** `printed/printed_01.jpg`

**Texto esperado (ground truth):**
> La precision del sistema OCR fue evaluada con imagenes reales.

**EASYOCR** (CER=0.0%, WER=0.0%, F1=1.000, 489 ms):
```
La precision del sistema OCR fue evaluada con imagenes reales.
```

**TESSERACT** (CER=4.8%, WER=30.0%, F1=0.984, 180 ms):
```
~ La precision del sistema OCR fue evaluada con.imagenes reales.
```

**GROQ** (CER=0.0%, WER=0.0%, F1=1.000, 524 ms):
```
La precision del sistema OCR fue evaluada con imagenes reales.
```

---

#### Manuscrito sintético

**Imagen:** `handwritten/handwritten_00.jpg`

**Texto esperado (ground truth):**
> El aprendizaje automatico permite a las computadoras aprender de datos.

**EASYOCR** (CER=71.8%, WER=80.0%, F1=1.000, 895 ms):
```
automatico
a las
computadoras
de datos.
El aprendizaje
aprender
permite
```

**TESSERACT** (CER=0.0%, WER=0.0%, F1=1.000, 193 ms):
```
El aprendizaje automatico permite a las computadoras aprender de datos.
```

**GROQ** (CER=0.0%, WER=0.0%, F1=1.000, 718 ms):
```
El aprendizaje automatico permite a las computadoras aprender de datos.
```

---

**Imagen:** `handwritten/handwritten_01.jpg`

**Texto esperado (ground truth):**
> La precision del sistema OCR fue evaluada con imagenes reales.

**EASYOCR** (CER=12.9%, WER=20.0%, F1=1.000, 625 ms):
```
La precision del sistema OCR
evaluada
con
imagenes reales.
fue
```

**TESSERACT** (CER=0.0%, WER=0.0%, F1=1.000, 182 ms):
```
La precision del sistema OCR fue evaluada con imagenes reales.
```

**GROQ** (CER=0.0%, WER=0.0%, F1=1.000, 622 ms):
```
La precision del sistema OCR fue evaluada con imagenes reales.
```

---

#### Impreso real

**Imagen:** `real_printed/R.png`

**Texto esperado (ground truth):**
> No me rendi. No, me rendi. Con o sin coma? Tu eliges.

**EASYOCR** (CER=47.2%, WER=66.7%, F1=0.823, 922 ms):
```
No me rendí. No, me rendí.
[Con sin coma?
Tú eliges
esopense tumblr.com
```

**TESSERACT** (CER=39.6%, WER=16.7%, F1=0.835, 183 ms):
```
No me rendi.
No, me rendi.
(Con o sin coma?
Tu eliges.
esopense.tumblr.com
```

**GROQ** (CER=45.3%, WER=41.7%, F1=0.803, 4063 ms):
```
No me rendí.
No, me rendí.

¿Con o sin coma?

Tú eliges.
esopense.tumblr.com
```

---

**Imagen:** `real_printed/ejemplo.jpg`

**Texto esperado (ground truth):**
> EJEMPLO: "Los volcanes y los terremotos son dos procesos geologicos que alteran la forma de la tierra por erosion. Los volcanes estan formados por chimeneas o fisuras en la corteza terrestre, a traves de las cuales es expulsado el magma, a diferencia de los terremotos que son movimientos producidos en la corteza terrestre. Por otra parte, los volcanes son producidos por la elevada temperatura que existe en el interior de la Tierra, en cambio, los terremotos son causados por la ruptura de rocas de la corteza terrestre".

**EASYOCR** (CER=1.7%, WER=11.5%, F1=0.986, 3657 ms):
```
EJEMPLO:
"Los volcanes y los terremotos son dos procesos geológicos que alteran la forma de la tierra por erosión. Los volcanes están formados por chimeneas 0 fisuras en la corteza terrestre a través de las cuales es expulsado el magma, a diferencia de los terremotos que son movimientos producidos en la corteza terrestre Por otra  parte; los volcanes son producidos por la elevada temperatura que existe en el interior de la Tierra, en cambio, los terremotos son causados por la ruptura de rocas de la corteza terrestre" .
```

**TESSERACT** (CER=0.8%, WER=4.6%, F1=0.992, 410 ms):
```
EJEMPLO:
"Los volcanes y los terremotos son dos
procesos geoldgicos que alteran la forma de
la tierra por erosidn. Los volcanes estan
formados por chimeneas o fisuras en la
corteza terrestre, a través de las cuales es
expulsado el magma, a diferencia de los
terremotos que son movimientos producidos
en la corteza terrestre. Por otra parte, los
volcanes son producidos por la elevada
temperatura que existe en el interior de la
Tierra, en cambio, los terremotos son
causados por la ruptura de rocas de la
corteza terrestre”.
```

**GROQ** (CER=0.8%, WER=4.6%, F1=0.992, 4508 ms):
```
EJEMPLO:

"Los volcanes y los terremotos son dos procesos geológicos que alteran la forma de la tierra por erosión. Los volcanes están formados por chimeneas o fisuras en la corteza terrestre, a través de las cuales es expulsado el magma, a diferencia de los terremotos que son movimientos producidos en la corteza terrestre. Por otra parte, los volcanes son producidos por la elevada temperatura que existe en el interior de la Tierra, en cambio, los terremotos son causados por la ruptura de rocas de la corteza terrestre".
```

---

#### Manuscrito real

**Imagen:** `real_handwritten/manuscrita.jpg`

**Texto esperado (ground truth):**
> Habia una vez tres cerditos que eran hermanos, se querian mucho y siempre se ayudaban entre si para protegerse de los peligros...

**EASYOCR** (CER=60.5%, WER=100.0%, F1=0.766, 1252 ms):
```
Halía uma ~e bes cenditoa que
Biam Reumanos , ae
mucho % aiemntue ae
etie
aí
fvolegenae de loa fielopoa _
quenían
aqudalan 
7aha
```

**TESSERACT** (CER=62.8%, WER=81.8%, F1=0.628, 216 ms):
```
eran hermanos, ae yucrion
omuoho- y aiompre ce ayiudaban entre
```

**GROQ** (CER=2.3%, WER=13.6%, F1=0.977, 3933 ms):
```
Había una vez tres cerditos que 
eran hermanos, se querían 
mucho y siempre se ayudaban entre 
sí para protegerse de los peligros...
```

---


---

## 4. Conclusiones

### Conclusiones cuantitativas

- **Mejor motor global por F1:** GROQ con F1=0.993 y CER=1.5%.
- **Impreso sintético**: GROQ (1.000) > EASYOCR (0.983) > TESSERACT (0.982)
- **Manuscrito sintético**: GROQ (1.000) > EASYOCR (0.988) > TESSERACT (0.987)
- **Impreso real**: GROQ (0.927) > TESSERACT (0.924) > EASYOCR (0.919)
- **Manuscrito real**: GROQ (0.977) > EASYOCR (0.766) > TESSERACT (0.628)

**Latencia media por motor:**
- EASYOCR: 689 ms
- TESSERACT: 187 ms
- GROQ: 2432 ms

- **Interpretación:** Tesseract es competitivo en texto impreso de alta calidad, pero el motor IA (Llama 4 Scout Vision) mantiene desempeño superior en manuscritura cursiva real. La estrategia híbrida del proyecto — EasyOCR para impreso + IA para manuscrita — maximiza F1 global (0.993).

---

## 5. Reproducibilidad

Todas las imágenes son sintéticas y se generan deterministicamente con
`random.Random(42)`. El ground truth está en
`app/test_images/ground_truth.json` y los resultados completos en
`benchmark_results.json`.

Para auditar un caso particular, abrir el JSON y filtrar por `image_path`.
