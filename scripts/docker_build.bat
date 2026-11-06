@echo off
rem Builds Sparky's images with its current content. Run this again after changing sheets, voice lines or faces.
title Build Sparky images
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\docker_prepare.py
) else (
    python scripts\docker_prepare.py
)
if errorlevel 1 (
    echo The content couldn't be prepared, so nothing was built.
    pause
    exit /b 1
)
docker compose build
if errorlevel 1 (
    echo The build failed.
    pause
    exit /b 1
)
echo.
echo Done. Note that a computer already running Sparky keeps its existing content.
echo To replace it with this build, including any changes made there: docker compose down -v
pause
