param(
    [string]$TunnelName = "dental-ai-mvp"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Cloudflared = Join-Path $ProjectRoot "tools\cloudflared.exe"
if (-not (Test-Path $Cloudflared)) {
    throw "Missing cloudflared.exe. Run .\scripts\install_cloudflared.ps1 first."
}

& $Cloudflared tunnel create $TunnelName
& $Cloudflared tunnel route dns $TunnelName demo.wtechx.tech
& $Cloudflared tunnel route dns $TunnelName api.wtechx.tech

Write-Host ""
Write-Host "Now create .cloudflared\config.yml from docs\cloudflared_config_example.yml"
Write-Host "Set tunnel to the UUID printed above and credentials-file to the generated JSON path."
