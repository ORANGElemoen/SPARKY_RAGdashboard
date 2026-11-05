# Sparky's control window: shows what is running and opens the tunnel.
# Started by start_sparky_server.bat. Closing this window leaves Sparky running.
$Host.UI.RawUI.WindowTitle = 'Sparky'
$HotspotAddress = '192.168.137.1'
$Policy = Join-Path $env:LOCALAPPDATA 'ngrok\sparky_policy.yml'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

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
    if ((Test-Path $Policy) -and -not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
        Start-Process cmd.exe -ArgumentList '/c', "`"$ScriptDir\start_ngrok.bat`"" -WindowStyle Minimized
    }
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

Start-Tunnel
$browserOpened = $false
$checkedUrl = $null
$loginCode = 0

while ($true) {
    $serverHost = Get-ServerHost
    $serverUrl = if ($serverHost) { "http://${serverHost}:8001" } else { $null }
    $serverUp = $serverUrl -and ((Get-StatusCode "$serverUrl/ui") -eq 200)
    $ollamaUp = (Get-StatusCode 'http://127.0.0.1:11434/api/tags') -eq 200
    $hotspotUp = [bool](Get-NetIPAddress -IPAddress $HotspotAddress -ErrorAction SilentlyContinue)
    $tunnelUrl = Get-TunnelUrl
    if ($tunnelUrl -and $tunnelUrl -ne $checkedUrl) {
        $loginCode = Get-StatusCode "$tunnelUrl/ui"   # counts against ngrok's quota, so only once
        $checkedUrl = $tunnelUrl
    }
    $boardAge = if ($serverUp) { Get-BoardStatus $serverUrl } else { $null }

    Clear-Host
    Write-Host ''
    Write-Host '  SPARKY' -ForegroundColor Cyan
    Write-Host ''
    if ($ollamaUp) { Write-Row 'AI model' 'OK' 'Ollama is running' } else { Write-Row 'AI model' 'WAIT' 'Waiting for Ollama' }
    if ($serverUp) { Write-Row 'Server' 'OK' $serverUrl } else { Write-Row 'Server' 'WAIT' 'Starting, this can take a minute' }
    if ($hotspotUp) { Write-Row 'Hotspot' 'OK' 'On' } else { Write-Row 'Hotspot' 'OFF' 'Sparky needs it for now: turn on Mobile hotspot, then restart' }
    if ($null -eq $boardAge) { Write-Row 'Board' 'OFF' 'Not seen yet' }
    elseif ($boardAge -lt 90) { Write-Row 'Board' 'OK' "Connected, seen $boardAge s ago" }
    else { Write-Row 'Board' 'OFF' "Last seen $([int]($boardAge / 60)) min ago" }

    if (-not (Test-Path $Policy)) { Write-Row 'Internet' 'OFF' 'Not set up: run scripts\setup_ngrok.bat' }
    elseif (-not $tunnelUrl) { Write-Row 'Internet' 'WAIT' 'Tunnel is not open yet. Press T to retry' }
    elseif ($loginCode -eq 401) { Write-Row 'Internet' 'OK' "$tunnelUrl  (login required)" }
    else { Write-Row 'Internet' 'FAIL' "$tunnelUrl  answered $loginCode, expected a login request. Press S" }

    Write-Host ''
    Write-Host '  O open dashboard   C copy internet address   T retry tunnel   S stop Sparky'
    Write-Host '  Closing this window leaves Sparky running.' -ForegroundColor DarkGray

    if ($serverUp -and -not $browserOpened) {
        Start-Process "$serverUrl/ui"
        $browserOpened = $true
    }

    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline) {
        if ([Console]::KeyAvailable) {
            switch ([Console]::ReadKey($true).Key) {
                'O' { if ($serverUrl) { Start-Process "$serverUrl/ui" } }
                'C' { if ($tunnelUrl) { Set-Clipboard $tunnelUrl } }
                'T' { Start-Tunnel }
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
