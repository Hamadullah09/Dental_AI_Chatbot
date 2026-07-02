param(
    [int]$Port = 8002,
    [string]$HostAddress = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $ProjectRoot
try {
    $Python = Join-Path $ProjectRoot ".run_venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        throw "Missing .run_venv. Create/install backend dependencies before starting."
    }
    & $Python -m uvicorn app.main:app --host $HostAddress --port $Port
}
finally {
    Pop-Location
}
