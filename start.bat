@echo off
setlocal
set "SCRIPT=%~dp0scripts\windows\start.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
endlocal
