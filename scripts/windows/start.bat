@echo off
setlocal
set "SCRIPT=%~dp0start.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
