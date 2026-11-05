@echo off
rem Double-click (or use the desktop shortcut) to start Ollama + Sparky's tutor server.
rem Close this window to stop the server (Ollama keeps running in the system tray).
rem The server listens on the laptop's hotspot, or only on this laptop when the hotspot is off.
rem It never listens on Ethernet or other Wi-Fi. The internet route goes through ngrok instead.
title Sparky server
cd /d "%~dp0.."

netstat -ano | findstr ":8001 " | findstr LISTENING >nul
if not errorlevel 1 (
    start "Sparky" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sparky_status.ps1"
    exit /b
)

rem Turn on the laptop's hotspot (works with no internet too), and wait for its address
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_hotspot.ps1"
set "API_HOST=127.0.0.1"
set /a tries=0
:waithotspot
ipconfig | findstr /r /c:"192\.168\.137\.1\>" >nul
if not errorlevel 1 (
    set "API_HOST=192.168.137.1"
    goto hotspotready
)
set /a tries+=1
if %tries% lss 10 (
    ping -n 2 127.0.0.1 >nul
    goto waithotspot
)
:hotspotready

rem Ollama (the AI) must be up before the server, which loads the model at start
curl.exe -s -o nul http://127.0.0.1:11434/api/tags
if errorlevel 1 (
    echo Starting Ollama...
    start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
)
set /a tries=0
:waitollama
curl.exe -s -o nul http://127.0.0.1:11434/api/tags && goto ollamaready
set /a tries+=1
if %tries% geq 30 (
    echo Ollama did not start - Sparky can't answer until it runs.
    goto ollamaready
)
timeout /t 1 >nul
goto waitollama
:ollamaready

rem The control window shows what is running and opens the tunnel. Press O there to open the dashboard.
start "Sparky" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sparky_status.ps1"
echo Sparky's server log. Stop Sparky from the control window.
rem Use the project's virtual environment when there is one
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" simple_api.py
) else (
    python simple_api.py
)
echo.
echo The server stopped.
pause
