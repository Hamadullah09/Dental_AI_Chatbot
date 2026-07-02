param(
    [string]$BackupRoot = "backups",
    [switch]$IncludeUploads,
    [switch]$IncludeQdrant
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Destination = Join-Path $ProjectRoot "$BackupRoot\mvp-$Timestamp"
New-Item -ItemType Directory -Path $Destination -Force | Out-Null

Push-Location $ProjectRoot
try {
    if (Test-Path "dental_ai.db") {
        Copy-Item -LiteralPath "dental_ai.db" -Destination (Join-Path $Destination "dental_ai.db") -Force
    }
    foreach ($sidecar in @("dental_ai.db-wal", "dental_ai.db-shm", ".env", "dataset_generation_status.json", "Database Q&A.csv")) {
        if (Test-Path $sidecar) {
            Copy-Item -LiteralPath $sidecar -Destination (Join-Path $Destination $sidecar) -Force
        }
    }

    if (Test-Path "uploaded_docs") {
        Get-ChildItem -Path "uploaded_docs" -Recurse |
            Select-Object FullName, Length, LastWriteTime |
            Export-Csv -NoTypeInformation -Path (Join-Path $Destination "uploaded_docs_manifest.csv")
        if ($IncludeUploads) {
            Copy-Item -Path "uploaded_docs" -Destination (Join-Path $Destination "uploaded_docs") -Recurse -Force
        }
    }

    if (Test-Path "qdrant_storage") {
        Get-ChildItem -Path "qdrant_storage" -Recurse |
            Select-Object FullName, Length, LastWriteTime |
            Export-Csv -NoTypeInformation -Path (Join-Path $Destination "qdrant_storage_manifest.csv")
        if ($IncludeQdrant) {
            Copy-Item -Path "qdrant_storage" -Destination (Join-Path $Destination "qdrant_storage") -Recurse -Force
        }
    }

    $summary = @{
        created_at = (Get-Date).ToString("o")
        project_root = $ProjectRoot.Path
        include_uploads = [bool]$IncludeUploads
        include_qdrant = [bool]$IncludeQdrant
        note = "Non-destructive backup. Uploaded PDFs and Qdrant are copied only when switches are used; manifests are always created."
    }
    $summary | ConvertTo-Json | Set-Content -Path (Join-Path $Destination "backup_summary.json") -Encoding UTF8
    Write-Host "Backup created: $Destination"
}
finally {
    Pop-Location
}
