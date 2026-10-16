@echo off
setlocal
rem Restart the V-Base preview stack from the repository root.
rem Forwarded to the same logic as apps/web/src/lib/start.sh.
cd /d "%~dp0\..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\start.ps1" --restart
endlocal
