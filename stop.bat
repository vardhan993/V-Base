@echo off
setlocal
set "SCRIPT=%~dp0scripts\windows\stop-backend.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
