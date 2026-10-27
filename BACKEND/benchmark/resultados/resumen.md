### iam_lineas

| Motor | N | CER corpus (IC 95%) | WER corpus (IC 95%) | CER estricto | WER estricto | CER medio por imagen | Tiempo medio | Mediana | p95 |
|---|---|---|---|---|---|---|---|---|---|
| easyocr | 150 | 46.0% (43.4%–48.4%) | 102.3% (98.3%–106.4%) | 50.9% | 110.1% | 46.0% | 1879 ms | 1777 ms | 3130 ms |
| groq | 150 | 2.6% (1.8%–3.3%) | 6.4% (4.8%–8.1%) | 4.5% | 11.4% | 2.6% | 17669 ms | 7665 ms | 71053 ms |
| tesseract | 150 | 50.9% (46.3%–55.4%) | 87.9% (83.0%–93.0%) | 54.9% | 93.0% | 50.9% | 619 ms | 586 ms | 935 ms |
| trocr | 150 | 1.4% (0.8%–2.1%) | 3.5% (2.3%–4.8%) | 1.8% | 6.4% | 1.3% | 3199 ms | 3149 ms | 4384 ms |

- easyocr: `easyocr 1.7.2` en Windows AMD64 AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD
- groq: `qwen/qwen3.8-27b` en Windows AMD64 AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD
- tesseract: `tesseract 5.5.0.20241111` en Windows AMD64 AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD
- trocr: `microsoft/trocr-base-handwritten (beams=1, transformers 4.57.6)` en Windows AMD64 AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD
