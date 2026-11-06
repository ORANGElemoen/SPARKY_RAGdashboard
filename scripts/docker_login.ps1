# Logs Docker in to GitHub's image store with a token from the clipboard. The token is never shown.
# Hidden paste prompts often receive nothing in the VS Code terminal, so this avoids them.
#   powershell -ExecutionPolicy Bypass -File scripts\docker_login.ps1
$account = 'ORANGElemoen'

Write-Host ''
Write-Host "Copy your GitHub token now (from github.com/settings/tokens), then come back here."
Read-Host 'Press Enter once it is copied' | Out-Null

$token = (Get-Clipboard | Out-String).Trim()
if (-not $token) {
    Write-Host 'The clipboard is empty. Copy the token and run this again.'
    exit 1
}
if ($token -notmatch '^ghp_[A-Za-z0-9_]+$') {
    Write-Host "The clipboard doesn't hold a classic GitHub token, which starts with ghp_ and has no spaces."
    Write-Host 'Make one at github.com/settings/tokens/new with write:packages ticked, and copy it again.'
    exit 1
}

try {
    $reply = Invoke-WebRequest 'https://api.github.com/user' -UseBasicParsing -Headers @{ Authorization = "Bearer $token" }
} catch {
    Write-Host "GitHub rejected that token: $($_.Exception.Message)"
    Write-Host 'It may be expired or mistyped. Make a new one at github.com/settings/tokens/new.'
    exit 1
}
$login = ($reply.Content | ConvertFrom-Json).login
$scopes = "$($reply.Headers['X-OAuth-Scopes'])"
Write-Host "Token belongs to: $login"
Write-Host "Permissions: $scopes"
if ($login -ne $account) {
    Write-Host "That's not $account. Sign in to GitHub as $account, and make the token there."
    exit 1
}
if ($scopes -notmatch 'packages') {
    Write-Host 'This token has no packages permission. Make a new one with write:packages ticked.'
    exit 1
}

$token | docker login ghcr.io -u $account --password-stdin
$result = $LASTEXITCODE
Set-Clipboard -Value ' '          # don't leave the token on the clipboard
exit $result
