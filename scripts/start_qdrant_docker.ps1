param(
    [string]$ComposeFile = "docker-compose.qdrant.yml"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ResolvedComposeFile = Join-Path $ProjectRoot $ComposeFile

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and make sure 'docker' is available in PATH."
}
if (-not (Test-Path $ResolvedComposeFile)) {
    throw "Missing compose file: $ResolvedComposeFile"
}

Push-Location $ProjectRoot
try {
    docker compose -f $ResolvedComposeFile up -d qdrant
    Write-Host "Qdrant Docker server is starting at http://127.0.0.1:6333"
    Write-Host "Check health with: curl http://127.0.0.1:6333/healthz"
}
finally {
    Pop-Location
}
