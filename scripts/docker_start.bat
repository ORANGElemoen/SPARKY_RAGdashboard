@echo off
rem Double-click to start Sparky in Docker. Your normal start_sparky_server.bat keeps working separately.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker_start.ps1"
