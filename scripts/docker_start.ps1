# Starts Sparky in Docker: the images, the hotspot, the graphics card if there is one, then the control window.
# Run scripts\docker_start.bat rather than this file. Any problem is explained in plain words.
$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.WindowTitle = 'Sparky'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

function Stop-WithMessage([string]$message) {
    Write-Host ''
    Write-Host "  $message" -ForegroundColor Yellow
    Write-Host ''
    Read-Host '  Press Enter to close' | Out-Null
    exit 1
}

function Test-Image([string]$name) {
    & docker image inspect $name 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

Write-Host ''
Write-Host '  Starting Sparky in Docker...' -ForegroundColor Cyan

$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-WithMessage 'Docker is not installed. Install Docker Desktop from docker.com, restart, and try again.'
}

# 1. Docker itself
& docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $desktop) {
        Write-Host '  Starting Docker Desktop, this can take a minute...'
        Start-Process $desktop
    }
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep 3
        & docker info 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Docker Desktop did not start. Open it, wait until it says it is running, and try again.' }
}

# 2. The images. If this computer doesn't have them: from a saved file, otherwise from GitHub.
if (-not ((Test-Image 'sparky:latest') -and (Test-Image 'sparky-ollama:latest'))) {
    $saved = Join-Path $Root 'sparky-images.tar'
    if (Test-Path $saved) {
        Write-Host '  Loading the images from sparky-images.tar. This takes several minutes, once only...'
        & docker load -i $saved
        if ($LASTEXITCODE -ne 0) { Stop-WithMessage "The images couldn't be loaded. Check that this drive has at least 25 GB free." }
    } else {
        Write-Host '  Downloading the images from GitHub, about 13 GB. This happens once only...'
        foreach ($name in 'sparky', 'sparky-ollama') {
            & docker pull "ghcr.io/orangelemoen/${name}:latest"
            if ($LASTEXITCODE -ne 0) {
                Stop-WithMessage "Couldn't download them. Log in first with: powershell -ExecutionPolicy Bypass -File scripts\docker_login.ps1"
            }
            & docker tag "ghcr.io/orangelemoen/${name}:latest" "${name}:latest"
        }
    }
}

# 3. The server already running outside Docker would have the same port
$native = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'simple_api' }
if ($native) { Stop-WithMessage "Sparky is already running outside Docker. Press S in its control window, then try again." }

# 4. The hotspot, and publish the server only there. If it can't start, stay on this computer only.
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ScriptDir 'start_hotspot.ps1')
$env:SPARKY_BIND = '127.0.0.1'
for ($i = 0; $i -lt 10; $i++) {
    if (Get-NetIPAddress -IPAddress '192.168.137.1' -ErrorAction SilentlyContinue) {
        $env:SPARKY_BIND = '192.168.137.1'
        break
    }
    Start-Sleep 1
}

# 5. Start, on the graphics card if this computer can use it
Write-Host '  Starting the containers...'
$started = $false
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    & docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --no-build
    $started = $LASTEXITCODE -eq 0
    if (-not $started) { Write-Host '  The graphics card could not be used. Trying without it, which is slower...' }
}
if (-not $started) {
    & docker compose up -d --no-build
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'The containers did not start. See the messages above.' }
    Write-Host '  Running without a graphics card: expect slower answers.' -ForegroundColor Yellow
    Start-Sleep 3
}

& (Join-Path $ScriptDir 'sparky_status.ps1') -Docker
