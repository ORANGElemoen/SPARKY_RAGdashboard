@echo off
rem Double-click (or use the desktop shortcut) to start Ollama + Sparky's tutor server.
rem Close this window to stop the server (Ollama keeps running in the system tray).
title Sparky server
cd /d "%~dp0.."

netstat -ano | findstr ":8001 " | findstr LISTENING >nul
if not errorlevel 1 (
    echo Sparky's server is already running - opening it in the browser.
    start "" http://127.0.0.1:8001/ui
    timeout /t 3 >nul
    exit /b
)

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

rem Open the browser once the server has had time to start
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep 10; Start-Process 'http://127.0.0.1:8001/ui'"
echo Starting Sparky's server... (close this window to stop it)
python simple_api.py
echo.
echo The server stopped.
pause
