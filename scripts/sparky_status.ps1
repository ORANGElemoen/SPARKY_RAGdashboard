# Sparky's control window: shows what is running and opens the tunnel.
# Started by start_sparky_server.bat, or docker_start.ps1 with -Docker. Closing this window leaves Sparky running.
param([switch]$Docker)
$Host.UI.RawUI.WindowTitle = 'Sparky'
$HotspotAddress = '192.168.137.1'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SecretsDir = Join-Path (Split-Path -Parent $ScriptDir) 'docker\secrets'
$Policy = if ($Docker) { Join-Path $SecretsDir 'policy.yml' } else { Join-Path $env:LOCALAPPDATA 'ngrok\sparky_policy.yml' }
$LocalOnlyMarker = if ($Docker) { Join-Path $SecretsDir 'local_only' } else { Join-Path $env:LOCALAPPDATA 'ngrok\sparky_local_only' }
if ($Docker) { Set-Location (Split-Path -Parent $ScriptDir) }
$speechReady = $false

function Get-StatusCode([string]$url) {
    # The header skips ngrok's browser warning page, so this sees the login check behind it
    $headers = @{ 'ngrok-skip-browser-warning' = '1' }
    try { return [int](Invoke-WebRequest $url -Headers $headers -UseBasicParsing -TimeoutSec 5).StatusCode }
    catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

function Get-ServerHost {
    $listener = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return $listener.LocalAddress }
    return $null
}

function Get-TunnelUrl {
    try {
        $tunnels = (Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2).tunnels
        return ($tunnels | Select-Object -First 1).public_url
    } catch { return $null }
}

function Start-Tunnel {
    if ($Docker) {
        if (Test-Path $Policy) { & docker compose --profile internet up -d --no-deps --no-build ngrok 2>&1 | Out-Null }
        return
    }
    if ((Test-Path $Policy) -and -not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
        Start-Process cmd.exe -ArgumentList '/c', "`"$ScriptDir\start_ngrok.bat`"" -WindowStyle Minimized
    }
}

# Asks for the ngrok token and a dashboard login, in this window.
function Set-UpInternet {
    Clear-Host
    if ($Docker) { & (Join-Path $ScriptDir 'setup_ngrok.ps1') -SecretsDir $SecretsDir }
    else { & (Join-Path $ScriptDir 'setup_ngrok.ps1') }
    if (Test-Path $Policy) {
        Remove-Item $LocalOnlyMarker -ErrorAction SilentlyContinue
        Start-Tunnel
    }
    Write-Host ''
    Read-Host 'Press Enter to go back' | Out-Null
}

# First run on this computer: internet access is optional, so pressing Enter is a real answer.
function Ask-AboutInternet {
    if ((Test-Path $Policy) -or (Test-Path $LocalOnlyMarker)) { return }
    Write-Host ''
    Write-Host '  Sparky works locally without internet access. The internet route is optional,'
    Write-Host '  and needs a free ngrok account.'
    Write-Host ''
    if ((Read-Host '  Set it up now? Type Y, or press Enter to run local only') -match '^\s*y') {
        Set-UpInternet
    } else {
        New-Item -ItemType Directory -Force (Split-Path $LocalOnlyMarker) | Out-Null
        New-Item -ItemType File -Force $LocalOnlyMarker | Out-Null
    }
}

# For a shared computer such as a lab machine: removes the ngrok token and the dashboard login.
function Forget-Internet {
    Write-Host ''
    if ((Read-Host '  Remove the ngrok token and dashboard login from this computer? Type YES to confirm') -cne 'YES') { return }
    if ($Docker) {
        & docker compose --profile internet rm -sf ngrok 2>&1 | Out-Null
        Remove-Item (Join-Path $SecretsDir 'ngrok.env'), $Policy -ErrorAction SilentlyContinue
    } else {
        Get-Process ngrok -ErrorAction SilentlyContinue | ForEach-Object { Stop-WithParents $_.Id }
        Remove-Item $Policy -ErrorAction SilentlyContinue
        $check = & ngrok config check 2>&1 | Out-String
        $found = [regex]::Match($check, '([A-Za-z]:[^\r\n]*ngrok\.yml)')
        if ($found.Success) { Remove-Item $found.Groups[1].Value.Trim() -ErrorAction SilentlyContinue }
    }
    New-Item -ItemType Directory -Force (Split-Path $LocalOnlyMarker) | Out-Null
    New-Item -ItemType File -Force $LocalOnlyMarker | Out-Null
    Write-Host ''
    Write-Host '  Done. If this was a shared computer, you can also reset your token on the ngrok dashboard.'
    Start-Sleep 3
}

function Get-BoardStatus([string]$serverUrl) {
    try {
        $devices = (Invoke-RestMethod "$serverUrl/admin/devices" -TimeoutSec 3).devices | Where-Object { -not $_.revoked_at -and $_.last_seen_at }
        if (-not $devices) { return $null }
        $seen = $devices | ForEach-Object {
            [DateTime]::SpecifyKind([DateTime]::Parse($_.last_seen_at), [DateTimeKind]::Utc)
        } | Sort-Object | Select-Object -Last 1
        return [int]((Get-Date).ToUniversalTime() - $seen).TotalSeconds
    } catch { return $null }
}

# Stops a process and the window it runs in, walking up through its Sparky parents.
function Stop-WithParents($processId) {
    $top = $processId
    while ($true) {
        $self = Get-CimInstance Win32_Process -Filter "ProcessId=$top" -ErrorAction SilentlyContinue
        if (-not $self) { break }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($self.ParentProcessId)" -ErrorAction SilentlyContinue
        if ($parent -and $parent.CommandLine -match 'start_sparky_server|start_ngrok|simple_api') { $top = $parent.ProcessId }
        else { break }
    }
    & taskkill.exe /PID $top /T /F | Out-Null
}

function Stop-Everything {
    if ($Docker) {
        & docker compose --profile internet down 2>&1 | Out-Null     # keeps the sparky-data volume
        return
    }
    Get-Process ngrok -ErrorAction SilentlyContinue | ForEach-Object { Stop-WithParents $_.Id }
    $listener = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { Stop-WithParents $listener.OwningProcess }
}

function Write-Row([string]$label, [string]$state, [string]$detail) {
    $color = @{ OK = 'Green'; WAIT = 'Yellow'; OFF = 'Yellow'; FAIL = 'Red' }[$state]
    Write-Host ('  {0,-10}' -f $label) -NoNewline
    Write-Host ('{0,-6}' -f $state) -ForegroundColor $color -NoNewline
    Write-Host $detail
}

Ask-AboutInternet
Start-Tunnel
$checkedUrl = $null
$loginCode = 0

while ($true) {
    $serverHost = Get-ServerHost
    $serverUrl = if ($serverHost) { "http://${serverHost}:8001" } else { $null }
    $serverUp = $serverUrl -and ((Get-StatusCode "$serverUrl/ui") -eq 200)
    if ($Docker) {
        $ollamaUp = [bool](& docker compose exec -T ollama ollama ps 2>$null | Select-Object -Skip 1)
        if (-not $speechReady) { $speechReady = [bool](& docker compose logs sparky 2>$null | Select-String 'Speech and search models are ready') }
        $serverUp = $serverUp -and $speechReady
    } else {
        $ollamaUp = (Get-StatusCode 'http://127.0.0.1:11434/api/tags') -eq 200
    }
    $hotspotUp = [bool](Get-NetIPAddress -IPAddress $HotspotAddress -ErrorAction SilentlyContinue)
    $tunnelUrl = Get-TunnelUrl
    if ($tunnelUrl -and ($tunnelUrl -ne $checkedUrl -or $loginCode -ne 401)) {
        $loginCode = Get-StatusCode "$tunnelUrl/ui"   # counts against ngrok's quota, so stop once it's confirmed
        $checkedUrl = $tunnelUrl
    }
    $boardAge = if ($serverUp) { Get-BoardStatus $serverUrl } else { $null }

    Clear-Host
    Write-Host ''
    Write-Host '  SPARKY' -ForegroundColor Cyan
    Write-Host ''
    if ($ollamaUp) { Write-Row 'AI model' 'OK' $(if ($Docker) { 'Loaded' } else { 'Ollama is running' }) }
    else { Write-Row 'AI model' 'WAIT' $(if ($Docker) { 'Loading, about a minute' } else { 'Waiting for Ollama' }) }
    if ($serverUp) { Write-Row 'Server' 'OK' $serverUrl } else { Write-Row 'Server' 'WAIT' 'Starting, this can take a minute' }
    if ($hotspotUp) { Write-Row 'Hotspot' 'OK' 'On' } else { Write-Row 'Hotspot' 'OFF' 'Could not start it. Sparky can only use the internet route' }
    if ($null -eq $boardAge) { Write-Row 'Board' 'OFF' 'Not seen yet' }
    elseif ($boardAge -lt 90) { Write-Row 'Board' 'OK' "Connected, seen $boardAge s ago" }
    else { Write-Row 'Board' 'OFF' "Last seen $([int]($boardAge / 60)) min ago" }

    if (-not (Test-Path $Policy)) { Write-Row 'Internet' 'OFF' 'Local only. Press N to set it up' }
    elseif (-not $tunnelUrl) { Write-Row 'Internet' 'WAIT' 'Tunnel is not open yet. Press T to retry' }
    elseif ($loginCode -eq 401) { Write-Row 'Internet' 'OK' "$tunnelUrl  (login required)" }
    elseif ($loginCode -ge 200 -and $loginCode -lt 400) { Write-Row 'Internet' 'FAIL' "$tunnelUrl  opened without a login! Press S" }
    else { Write-Row 'Internet' 'WAIT' "$tunnelUrl  checking the login..." }

    Write-Host ''
    Write-Host '  O open dashboard   C copy internet address   T retry tunnel   S stop Sparky'
    Write-Host '  N set up internet access   F forget my internet login'
    Write-Host '  Closing this window leaves Sparky running.' -ForegroundColor DarkGray

    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline) {
        if ([Console]::KeyAvailable) {
            switch ([Console]::ReadKey($true).Key) {
                'O' { if ($serverUrl) { Start-Process "$serverUrl/ui" } }
                'C' { if ($tunnelUrl) { Set-Clipboard $tunnelUrl } }
                'T' { Start-Tunnel }
                'N' { Set-UpInternet }
                'F' { Forget-Internet; $checkedUrl = $null; $loginCode = 0 }
                'S' {
                    Write-Host ''
                    Write-Host '  Stopping Sparky...'
                    Stop-Everything
                    Start-Sleep 2
                    exit
                }
            }
            break
        }
        Start-Sleep -Milliseconds 150
    }
}
