@echo off
setlocal
set "SCRIPT=%~dp0backup.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
