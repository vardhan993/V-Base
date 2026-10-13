@echo off
setlocal
set "SCRIPT=%~dp0stop-backend.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
