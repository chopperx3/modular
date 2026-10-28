# Afina TrOCR con los renglones sintéticos en español (CPU, ~4-5 horas).
# Si se interrumpe, volver a correr este mismo script: sigue desde el último punto guardado.
# Para detenerlo de forma ordenada: crear un archivo vacío app\models\trocr-es\DETENER
#
# Uso (desde BACKEND\):  .\entrenamiento\entrenar.ps1

Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:TRANSFORMERS_VERBOSITY = "error"

if (-not (Test-Path "entrenamiento\datos\sintetico_es\manifest.json")) {
    & .venv\Scripts\python.exe -m entrenamiento.generar_sintetico --n 6000
}

# Python mismo copia la salida al log (sin tuberías de PowerShell, que bloquean el archivo).
& .venv\Scripts\python.exe -m entrenamiento.afinar_trocr `
    --datos entrenamiento/datos/sintetico_es `
    --congelar-codificador --epocas 2 --lote 8 --acumular 2 `
    --eval-cada 100 --max-val 100 --reanudar `
    --log entrenamiento/datos/entrenamiento.log
