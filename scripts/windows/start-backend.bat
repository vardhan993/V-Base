@echo off
setlocal
set "ROOT=%~dp0.."
set "SCRIPT=%~dp0start-backend.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
