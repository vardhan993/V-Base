# V-Base - create and verify a PostgreSQL backup.
#
# Uses the same code path as the API (`nexus.commands.backup`): a physical
# pg_dump custom-format archive when pg_dump is on PATH, otherwise a portable
# JSON snapshot. Every artifact is parsed before it is reported as good, so a
# corrupt or truncated backup can never look like a success.
#
# Usage:
#   scripts\windows\backup.bat                # create a backup and verify it
#   scripts\windows\backup.bat list           # list backups with validation
#   scripts\windows\backup.bat restore FILE   # restore a JSON snapshot
param(
    [Parameter(Position = 0)]
    [ValidateSet("create", "list", "restore", "verify")]
    [string]$Command = "create",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { $venvPy = "python" }

$env:PYTHONPATH = (Join-Path $root "backend\src")

$cliArgs = @("-m", "nexus.commands.backup", $Command)
if ($Rest) { $cliArgs += $Rest }

& $venvPy @cliArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backup command failed. Check that PostgreSQL is reachable with the DATABASE_URL in backend\.env."
    exit $LASTEXITCODE
}
