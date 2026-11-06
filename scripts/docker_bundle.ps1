# Saves everything a new computer needs into one folder, for example on a USB stick.
#   powershell -ExecutionPolicy Bypass -File scripts\docker_bundle.ps1 E:\
# Holds Sparky's content but no ngrok token or login. Keep it private anyway.
param([Parameter(Mandatory = $true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Images = 'sparky:latest', 'sparky-ollama:latest', 'ngrok/ngrok:latest'
$NeededGB = 18

try {
    $drive = (Get-Item $Destination).PSDrive
    if ($drive.Free / 1GB -lt $NeededGB) {
        throw "$($drive.Name): has $([math]::Round($drive.Free / 1GB, 1)) GB free, and this needs about $NeededGB GB."
    }
    $bundle = Join-Path $Destination 'Sparky-Docker'
    New-Item -ItemType Directory -Force (Join-Path $bundle 'scripts'), (Join-Path $bundle 'docker') | Out-Null
    foreach ($name in 'docker-compose.yml', 'docker-compose.gpu.yml') {
        Copy-Item (Join-Path $Root $name) $bundle -Force
    }
    foreach ($name in 'docker_start.bat', 'docker_start.ps1', 'docker_login.ps1', 'start_hotspot.ps1', 'sparky_status.ps1', 'setup_ngrok.ps1') {
        Copy-Item (Join-Path $Root "scripts\$name") (Join-Path $bundle 'scripts') -Force
    }
    Copy-Item (Join-Path $Root 'docker\ollama.Dockerfile'), (Join-Path $Root 'docker\Dockerfile') (Join-Path $bundle 'docker') -Force

    foreach ($image in $Images) {
        & docker image inspect $image 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            if ($image -like 'ngrok/*') { & docker pull $image } else { throw "$image isn't built yet. Run scripts\docker_build.bat first." }
            if ($LASTEXITCODE -ne 0) { throw "Couldn't get $image." }
        }
    }
    Write-Host 'Saving the images. This takes several minutes...'
    $tar = Join-Path $bundle 'sparky-images.tar'
    & docker save -o $tar @Images
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $tar -ErrorAction SilentlyContinue
        throw 'Saving the images failed.'
    }
    Write-Host "Done: $bundle ($([math]::Round((Get-Item $tar).Length / 1GB, 1)) GB)"
    Write-Host 'On a new computer: install Docker Desktop, then double-click scripts\docker_start.bat in that folder.'
}
catch {
    Write-Host "Bundle not made: $($_.Exception.Message)"
    exit 1
}
