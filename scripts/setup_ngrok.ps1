# One-time ngrok setup. Run scripts\setup_ngrok.bat rather than this file.
# Asks for your ngrok token and a dashboard login, and stores them outside this public
# repository, in %LOCALAPPDATA%\ngrok. Run it again to change the login.
$ErrorActionPreference = 'Stop'

function Read-Secret([string]$prompt) {
    $secure = Read-Host $prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "ngrok isn't installed. Run: winget install --id Ngrok.Ngrok --exact"
    exit 1
}

Write-Host ""
Write-Host "Step 1 of 2: your ngrok token"
Write-Host "Copy it from https://dashboard.ngrok.com/get-started/your-authtoken"
Write-Host "Nothing shows on screen as you paste. Press Enter to keep the token already saved."
$token = (Read-Secret "Token").Trim()
if ($token) {
    & ngrok config add-authtoken $token | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "ngrok rejected that token."; exit 1 }
    Write-Host "Token saved."
}

Write-Host ""
Write-Host "Step 2 of 2: the login for your dashboard"
Write-Host "Anyone with this login can change Sparky and read the question log."
do {
    $user = (Read-Host "Username").Trim()
    if (-not $user -or $user.Contains(':')) { Write-Host "Enter a username without a colon." }
} while (-not $user -or $user.Contains(':'))
while ($true) {
    $password = Read-Secret "Password (at least 12 characters)"
    if ($password.Length -lt 12 -or $password.Length -gt 128) {
        Write-Host "Use 12 to 128 characters."
        continue
    }
    if ($password -ne (Read-Secret "Type it again")) {
        Write-Host "Those didn't match. Try again."
        continue
    }
    break
}

$credential = ("{0}:{1}" -f $user, $password).Replace("'", "''")
$policy = @"
on_http_request:
  # Sparky can't type a password: these paths check its device key instead
  - expressions:
      - "!req.url.path.startsWith('/api/v1/device/') && req.url.path != '/api/v1/voice/query'"
    actions:
      - type: basic-auth
        config:
          realm: Sparky
          credentials:
            - '$credential'
"@
$dir = Join-Path $env:LOCALAPPDATA 'ngrok'
New-Item -ItemType Directory -Force $dir | Out-Null
[IO.File]::WriteAllText((Join-Path $dir 'sparky_policy.yml'), $policy, (New-Object Text.UTF8Encoding($false)))

Write-Host ""
Write-Host "Done. Your login is saved in $dir\sparky_policy.yml"
Write-Host "Start Sparky's server, then run scripts\start_ngrok.bat"
