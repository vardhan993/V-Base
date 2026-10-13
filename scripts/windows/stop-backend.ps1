# V-Base - stop the locally started API and frontend.
#
# Prefers the PID files written by start.bat, then falls back to whatever owns
# the app ports. It never kills unrelated python.exe/node.exe processes.
$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$runDir = Join-Path $root ".run"

function Stop-FromPidFile([string]$label, [string]$file) {
    if (-not (Test-Path $file)) { return }
    $raw = (Get-Content $file -ErrorAction SilentlyContinue | Select-Object -First 1)
    # PID files are only trusted when they hold a plain integer.
    if ($raw -notmatch '^\s*\d+\s*$') { Remove-Item $file -Force -ErrorAction SilentlyContinue; return }
    $pidValue = [int]$raw.Trim()
    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Stopping $label (PID $pidValue, $($proc.ProcessName))"
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $file -Force -ErrorAction SilentlyContinue
}

Write-Host "Stopping V-Base ..."
if (Test-Path $runDir) {
    Stop-FromPidFile "API" (Join-Path $runDir "backend.pid")
    Stop-FromPidFile "frontend" (Join-Path $runDir "frontend.pid")
}

# Fallback for processes started outside start.bat.
foreach ($port in @(8000, 5173)) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $conns) {
            $owner = $conn.OwningProcess
            if (-not $owner -or $owner -le 0) { continue }
            $proc = Get-Process -Id $owner -ErrorAction SilentlyContinue
            if (-not $proc) { continue }
            if ($proc.ProcessName -notin @("python", "pythonw", "node", "uvicorn")) { continue }
            Write-Host "Stopping $($proc.ProcessName) (PID $owner) listening on port $port"
            Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
        }
    } catch { }
}

Write-Host "Done. The PostgreSQL container keeps running - use scripts\windows\postgres.bat stop to stop it too."
