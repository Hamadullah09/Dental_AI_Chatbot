param(
    [int]$Port = 3001,
    [string]$ApiUrl = "http://127.0.0.1:8002"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$RootEnvPath = Join-Path $ProjectRoot ".env"

function Import-EnvValueIfMissing {
    param(
        [string]$Name
    )

    if ([Environment]::GetEnvironmentVariable($Name, "Process")) {
        return
    }
    if (-not (Test-Path $RootEnvPath)) {
        return
    }

    $line = Get-Content $RootEnvPath | Where-Object { $_ -match "^\s*$Name\s*=" } | Select-Object -First 1
    if (-not $line) {
        return
    }

    $value = ($line -replace "^\s*$Name\s*=", "").Trim().Trim('"').Trim("'")
    if ($value) {
        [Environment]::SetEnvironmentVariable($Name, $value, "Process")
    }
}

Push-Location $FrontendRoot
try {
    $env:API_PROXY_URL = $ApiUrl.Trim('"').Trim("'")
    Import-EnvValueIfMissing "BACKUP_OPENAI_API_KEY"
    Import-EnvValueIfMissing "BACKUP_OPENAI_MODEL"
    Import-EnvValueIfMissing "BACKUP_OPENAI_TIMEOUT_MS"
    Import-EnvValueIfMissing "NEXT_PUBLIC_BACKUP_OPENAI_ENDPOINT"
    Import-EnvValueIfMissing "NEXT_PUBLIC_BACKEND_HEALTH_TIMEOUT_MS"
    Import-EnvValueIfMissing "NEXT_PUBLIC_CHAT_GENERATION_TIMEOUT_MS"
    Import-EnvValueIfMissing "NEXT_PUBLIC_OPENAI_BACKUP_TIMEOUT_MS"
    Import-EnvValueIfMissing "OPENAI_API_KEY"
    Import-EnvValueIfMissing "OPENAI_MODEL"
    Remove-Item Env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
    npm run dev -- -p $Port
}
finally {
    Pop-Location
}
