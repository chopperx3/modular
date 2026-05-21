param(
    [string]$Image       = "manuscrita.jpg",
    [string]$GroundTruth = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot   = $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "BACKEND"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "  [X]  $msg" -ForegroundColor Red }

if (-not (Test-Path $VenvPython)) {
    Write-Err "No existe el venv en $VenvPython"
    Write-Host "  Crearlo con: python -m venv .venv ; .\.venv\Scripts\pip install -r BACKEND\requirements.txt"
    exit 1
}
Write-Ok "Python venv encontrado"

if (-not (Test-Path (Join-Path $BackendDir ".env"))) {
    Write-Err "No existe BACKEND\.env (copialo de BACKEND\.env.example)"
    exit 1
}
Write-Ok ".env presente"

if (-not (Test-Path $Image)) {
    $alt = Join-Path $RepoRoot $Image
    if (Test-Path $alt) {
        $Image = $alt
    } else {
        Write-Err "No se encontro la imagen: $Image"
        exit 1
    }
}
$Image = (Resolve-Path $Image).Path
Write-Ok "Imagen: $Image"

Push-Location $BackendDir
try {
    if ([string]::IsNullOrWhiteSpace($GroundTruth)) {
        & $VenvPython -m app.demo --image $Image
    } else {
        & $VenvPython -m app.demo --image $Image --ground-truth $GroundTruth
    }
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($exitCode -ne 0) {
    Write-Err "El demo fallo con codigo $exitCode"
    exit $exitCode
}

Write-Host ""
Write-Host "  Para ver el reporte completo (34 imagenes):" -ForegroundColor Gray
Write-Host "    notepad RESULTADOS_BENCHMARK.md" -ForegroundColor Gray
Write-Host "  Para arrancar el backend completo:" -ForegroundColor Gray
Write-Host "    cd BACKEND ; uvicorn app.main:app --host 0.0.0.0 --port 8000" -ForegroundColor Gray
Write-Host ""
