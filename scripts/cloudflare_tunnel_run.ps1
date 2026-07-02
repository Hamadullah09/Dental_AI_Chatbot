param(
    [string]$ConfigPath = ".cloudflared\config.yml"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Cloudflared = Join-Path $ProjectRoot "tools\cloudflared.exe"
$ResolvedConfig = Join-Path $ProjectRoot $ConfigPath
if (-not (Test-Path $Cloudflared)) {
    throw "Missing cloudflared.exe. Run .\scripts\install_cloudflared.ps1 first."
}
if (-not (Test-Path $ResolvedConfig)) {
    throw "Missing tunnel config: $ResolvedConfig"
}
& $Cloudflared tunnel --config $ResolvedConfig run
