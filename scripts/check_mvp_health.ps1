param(
    [string]$BackendUrl = "http://127.0.0.1:8002",
    [string]$FrontendUrl = "http://127.0.0.1:3001",
    [string]$OllamaUrl = "http://192.168.1.2:11434"
)

$ErrorActionPreference = "Continue"

Write-Host "Backend:"
try { (Invoke-WebRequest "$BackendUrl/api/health" -UseBasicParsing -TimeoutSec 10).Content } catch { Write-Host $_.Exception.Message }

Write-Host "`nFrontend:"
try { (Invoke-WebRequest "$FrontendUrl/login" -UseBasicParsing -TimeoutSec 10).StatusCode } catch { Write-Host $_.Exception.Message }

Write-Host "`nOllama:"
try { (Invoke-WebRequest "$OllamaUrl/api/tags" -UseBasicParsing -TimeoutSec 10).Content } catch { Write-Host $_.Exception.Message }
