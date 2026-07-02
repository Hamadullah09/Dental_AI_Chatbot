$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Cloudflared = Join-Path $ProjectRoot "tools\cloudflared.exe"
if (-not (Test-Path $Cloudflared)) {
    throw "Missing cloudflared.exe. Run .\scripts\install_cloudflared.ps1 first."
}
& $Cloudflared tunnel login
