@echo off
rem Opens the internet route to Sparky's running server, behind the login from setup_ngrok.bat.
rem Close this window to close the route. The hotspot route keeps working either way.
title Sparky ngrok tunnel
set "POLICY=%LOCALAPPDATA%\ngrok\sparky_policy.yml"

if not exist "%POLICY%" (
    echo No login is set up yet, so the tunnel was not opened. Run scripts\setup_ngrok.bat first.
    pause
    exit /b 1
)

rem The server may still be starting, so give it up to a minute
set /a tries=0
:findserver
set "TARGET="
netstat -ano | findstr "192.168.137.1:8001 " | findstr LISTENING >nul
if not errorlevel 1 set "TARGET=192.168.137.1:8001"
if not defined TARGET (
    netstat -ano | findstr /r /c:"127.0.0.1:8001 " /c:"0.0.0.0:8001 " | findstr LISTENING >nul
    if not errorlevel 1 set "TARGET=127.0.0.1:8001"
)
if not defined TARGET (
    set /a tries+=1
    if %tries% geq 30 (
        echo Sparky's server isn't running. Start it first, then run this again.
        pause
        exit /b 1
    )
    ping -n 3 127.0.0.1 >nul
    goto findserver
)

echo Opening the tunnel to %TARGET%. Your address is on the "Forwarding" line below.
ngrok http %TARGET% --traffic-policy-file "%POLICY%"
echo.
echo The tunnel closed.
pause
