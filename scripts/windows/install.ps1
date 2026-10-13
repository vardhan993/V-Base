# V-Base - one-time local setup for Windows.
#
# Creates .venv, installs the backend (FastAPI + PostgreSQL drivers), creates
# the environment files from their templates, and installs the frontend.
# It never overwrites an existing .env file and never installs a paid service.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
Write-Host "=== V-Base - install ===" -ForegroundColor Cyan

# ---------------------------------------------------------------- Python ----
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Error "Python 3.12+ was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') and re-run install.bat."
    exit 1
}
$version = & $python.Source --version
Write-Host "Found $version"

$venvDir = Join-Path $root ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating virtual environment in .venv ..."
    & $python.Source -m venv $venvDir
}

Write-Host "Installing backend dependencies ..."
& $venvPy -m pip install --upgrade pip setuptools wheel --quiet
# Editable install: this is what puts the `nexus` package (and the vbase-* 
# console scripts) on the venv's path, so `python -m nexus.commands.*` and the
# installed `vbase-run` / `vbase-migrate` / `vbase-admin` / `vbase-backup`
# entry points all work from any directory.
& $venvPy -m pip install -e "$root\backend[dev]"
if ($LASTEXITCODE -ne 0) { Write-Error "Backend install failed. Fix the pip output above and re-run."; exit 1 }

# --------------------------------------------------------- environment ------
$backendEnv = Join-Path $root "backend\.env"
if (-not (Test-Path $backendEnv)) {
    Copy-Item (Join-Path $root "backend\.env.example") $backendEnv
    Write-Host "Created backend\.env from the template." -ForegroundColor Green
} else {
    Write-Host "backend\.env already exists - left untouched."
}
$frontendEnv = Join-Path $root "apps\web\.env"
if (-not (Test-Path $frontendEnv)) {
    Copy-Item (Join-Path $root "apps\web\.env.example") $frontendEnv
    Write-Host "Created apps\web\.env from the template." -ForegroundColor Green
}

# ------------------------------------------------------------ frontend ------
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Warning "npm was not found. Install Node.js 20+ from https://nodejs.org/ to build the frontend, then re-run install.bat."
} else {
    Write-Host "Installing frontend dependencies ..."
    Push-Location (Join-Path $root "apps\web")
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) { Write-Error "npm install failed."; exit 1 }
    } finally { Pop-Location }
}

# ---------------------------------------------------------- PostgreSQL ------
$docker = Get-Command docker -ErrorAction SilentlyContinue
Write-Host ""
if ($docker) {
    Write-Host "Next: start the local PostgreSQL container, then migrate." -ForegroundColor Cyan
    Write-Host "  scripts\windows\postgres.bat     # starts PostgreSQL 16 on port 5433"
    Write-Host "  scripts\windows\migrate.bat      # applies the schema (alembic upgrade head)"
} else {
    Write-Host "Docker was not found. Start PostgreSQL yourself and set DATABASE_URL in backend\.env." -ForegroundColor Yellow
    Write-Host "Then run: scripts\windows\migrate.bat"
}

Write-Host ""
Write-Host "Install complete. Run start.bat to launch V-Base." -ForegroundColor Green
