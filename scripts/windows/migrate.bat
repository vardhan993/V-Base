@echo off
setlocal
set "SCRIPT=%~dp0migrate.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
