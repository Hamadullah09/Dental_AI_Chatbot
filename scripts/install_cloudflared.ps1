$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ToolsDir = Join-Path $ProjectRoot "tools"
$Cloudflared = Join-Path $ToolsDir "cloudflared.exe"
New-Item -ItemType Directory -Path $ToolsDir -Force | Out-Null

if (Test-Path $Cloudflared) {
    Write-Host "cloudflared already exists: $Cloudflared"
    & $Cloudflared --version
    exit 0
}

$Url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
Write-Host "Downloading cloudflared from $Url"
Invoke-WebRequest $Url -OutFile $Cloudflared -UseBasicParsing
Write-Host "Installed: $Cloudflared"
& $Cloudflared --version
