param(
    [int]$Port = 3001,
    [string]$ApiUrl = "http://127.0.0.1:8002"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $ProjectRoot "frontend"
Push-Location $FrontendRoot
try {
    $env:NEXT_PUBLIC_API_URL = $ApiUrl.Trim('"').Trim("'")
    npm run dev -- -p $Port
}
finally {
    Pop-Location
}
