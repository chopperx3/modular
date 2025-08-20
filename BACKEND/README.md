# Backend OCR (FastAPI)

## Dev quickstart
```bash
cd BACKEND
python -m venv .venv

.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000


### Cómo probar rápido
1) Arranca:  
`uvicorn app.main:app --reload --port 8000`  
2) Prueba en Swagger:  
`http://127.0.0.1:8000/ui/`  
3) `POST /ocr` con una imagen manuscrita (puede ser tu `manuscrita.jpg` del repo).  
4) Consulta `GET /results` y luego `GET /results/{id}` hasta que `estatus` cambie a **Procesado** y veas el texto.
