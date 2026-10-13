@echo off
setlocal
set "SCRIPT=%~dp0scripts\windows\postgres.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
