@echo off
setlocal
set "SCRIPT=%~dp0scripts\windows\backup.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
