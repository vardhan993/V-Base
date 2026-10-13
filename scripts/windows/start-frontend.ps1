# V-Base - start only the Vite dev server.
#
# Use this when the API already runs elsewhere: set VITE_API_BASE in
# apps\web\.env to that API's origin (for example a Render deployment) and run
# this script.
param(
    [int]$Port = 5173
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$frontendDir = Join-Path $root "apps\web"

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Error "npm was not found. Install Node.js 20+ from https://nodejs.org/."
    exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
    Write-Error "apps\web\package.json not found."
    exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "node_modules missing - running npm install ..."
    Push-Location $frontendDir
    try { & npm install } finally { Pop-Location }
}

Write-Host "Starting the frontend on http://localhost:$Port" -ForegroundColor Green
Push-Location $frontendDir
try { & npm run dev -- --port $Port } finally { Pop-Location }
