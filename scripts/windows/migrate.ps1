# V-Base - apply PostgreSQL schema migrations.
#
# Wraps `nexus.commands.migrate` so the schema is changed the same way locally,
# in CI and on the host. Alembic is the only supported way to alter the schema;
# the application never issues DDL at runtime.
#
# Usage:
#   scripts\windows\migrate.bat                 # upgrade to head
#   scripts\windows\migrate.bat current         # show the applied revision
#   scripts\windows\migrate.bat check           # detect model/migration drift
#   scripts\windows\migrate.bat revision -m "add x" --autogenerate
param(
    [Parameter(Position = 0)]
    [ValidateSet("upgrade", "current", "history", "check", "revision", "downgrade", "stamp")]
    [string]$Command = "upgrade",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { $venvPy = "python" }

# The migration wrapper resolves alembic.ini relative to the package, so it can
# run from the repository root regardless of the current directory.
$env:PYTHONPATH = (Join-Path $root "backend\src")

$cliArgs = @("-m", "nexus.commands.migrate", $Command)
if ($Rest) { $cliArgs += $Rest }

& $venvPy @cliArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Migration command failed. Is PostgreSQL running (scripts\windows\postgres.bat) and DATABASE_URL correct in backend\.env?"
    exit $LASTEXITCODE
}
