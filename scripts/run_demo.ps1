param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    $systemPython = Get-Command python -ErrorAction Stop
    & $systemPython.Source -m venv .venv
}

& $venvPython -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r requirements.txt
}

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Stop the existing process or pass an unused -Port value."
}

Write-Output "SourceCut seed demo: http://127.0.0.1:$Port"
& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port
