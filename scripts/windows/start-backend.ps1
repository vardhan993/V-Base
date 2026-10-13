# V-Base - start only the API (no frontend).
#
# Useful for running the SPA separately, or for pointing a deployed frontend at
# a local API. Prefer start.bat for everyday development.
param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { $venvPy = "python" }

$env:PYTHONPATH = (Join-Path $root "backend\src")

Write-Host "Applying migrations ..." -ForegroundColor Green
& $venvPy -m nexus.commands.migrate upgrade
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Starting the V-Base API on http://$HostName`:$Port" -ForegroundColor Green
& $venvPy -m uvicorn nexus.app:app --host $HostName --port $Port --log-level info
