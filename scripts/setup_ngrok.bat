@echo off
rem One-time ngrok setup: asks for your token and a dashboard login in this window.
title Sparky ngrok setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_ngrok.ps1"
echo.
pause
