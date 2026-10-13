# V-Base - local launcher.
#
# Verifies PostgreSQL is reachable, applies any pending migrations, then starts
# the API (uvicorn) and the Vite dev server. PID files are written so stop.bat
# can shut down exactly these processes and nothing else.
$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$runDir = Join-Path $root ".run"
if (-not (Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir -Force | Out-Null }

$backendHost = "127.0.0.1"
$backendPort = 8000
$frontendPort = 5173

Write-Host "=== V-Base - Your Business Data. One Powerful Base. ===" -ForegroundColor Cyan

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { $venvPy = "python" }
$env:PYTHONPATH = (Join-Path $root "backend\src")

# ------------------------------------------------------- PostgreSQL check ---
Write-Host "Checking PostgreSQL ..." -ForegroundColor Green
& $venvPy -c "import asyncio, sys; sys.path.insert(0, r'$root\backend\src'); from nexus.core.db import database_health; r = asyncio.run(database_health()); print('database:', r['status']); sys.exit(0 if r['status'] == 'ok' else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Warning "PostgreSQL is not reachable with the DATABASE_URL in backend\.env."
    Write-Host "Start the bundled development database with:"
    Write-Host "    scripts\windows\postgres.bat" -ForegroundColor Yellow
    Write-Host "or point DATABASE_URL at your own PostgreSQL instance."
    exit 1
}

# ------------------------------------------------------------- migrations ---
Write-Host "Applying migrations (alembic upgrade head) ..." -ForegroundColor Green
& $venvPy -m nexus.commands.migrate upgrade
if ($LASTEXITCODE -ne 0) {
    Write-Error "Migrations failed. Resolve the error above before starting the API."
    exit 1
}

# ----------------------------------------------------------------- backend ---
Write-Host "Starting the API on http://$backendHost`:$backendPort ..." -ForegroundColor Green
$backendProc = Start-Process -FilePath $venvPy `
    -ArgumentList "-m", "uvicorn", "nexus.app:app", "--host", $backendHost, "--port", "$backendPort", "--log-level", "info" `
    -PassThru -NoNewWindow -WorkingDirectory $root
$backendProc.Id | Set-Content (Join-Path $runDir "backend.pid")

Start-Sleep -Seconds 2
if ($backendProc.HasExited) {
    Write-Error "The API exited immediately. Check the output above (usually a bad DATABASE_URL or SECRET_KEY)."
    exit 1
}

# ---------------------------------------------------------------- frontend ---
$frontendDir = Join-Path $root "apps\web"
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
    Write-Warning "apps\web\package.json not found; skipping the frontend."
} elseif (-not $npm) {
    Write-Warning "npm not found; skipping the frontend. Install Node.js 20+."
} else {
    Write-Host "Starting the frontend on http://localhost:$frontendPort ..." -ForegroundColor Green
    $frontendProc = Start-Process -FilePath $npm.Source -ArgumentList "run", "dev" -PassThru -NoNewWindow -WorkingDirectory $frontendDir
    $frontendProc.Id | Set-Content (Join-Path $runDir "frontend.pid")
}

Write-Host ""
Write-Host "Frontend : http://localhost:$frontendPort" -ForegroundColor Cyan
Write-Host "API docs : http://$backendHost`:$backendPort/docs" -ForegroundColor Cyan
Write-Host "Readiness: http://$backendHost`:$backendPort/health/ready" -ForegroundColor Cyan
Write-Host "API PID  : $($backendProc.Id)  (stop everything with stop.bat)"
