@echo off
setlocal
set "SCRIPT=%~dp0postgres.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
