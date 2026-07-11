param(
    [string]$QdrantUrl = "http://127.0.0.1:6333",
    [string]$TargetCollection = "dental_docs_clean",
    [switch]$ReplaceTarget
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".run_venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Missing Python venv at $Python"
}

try {
    $health = Invoke-WebRequest -UseBasicParsing "$QdrantUrl/healthz" -TimeoutSec 5
    if ($health.StatusCode -ge 400) {
        throw "Qdrant health check returned HTTP $($health.StatusCode)"
    }
}
catch {
    throw "Qdrant server is not reachable at $QdrantUrl. Run .\scripts\start_qdrant_docker.ps1 first."
}

Push-Location $ProjectRoot
try {
    $env:QDRANT_URL = $QdrantUrl
    $env:QDRANT_LOCAL_PATH = ""
    $env:QDRANT_COLLECTION = "dental_docs"

    $args = @(
        "scripts\rebuild_clean_qdrant.py",
        "--target-collection",
        $TargetCollection,
        "--apply"
    )
    if ($ReplaceTarget) {
        $args += "--replace-target"
    }

    & $Python @args
}
finally {
    Pop-Location
}
