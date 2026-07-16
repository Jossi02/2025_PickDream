param(
    [Parameter(Mandatory = $true)]
    [string]$CredentialPath,

    [string]$Project = "pickdreamtest",

    [switch]$Apply
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $CredentialPath)) {
    throw "Service account key file not found: $CredentialPath"
}

$python = Join-Path $PSScriptRoot "..\functions\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Functions virtual environment not found: $python"
}

$env:GOOGLE_APPLICATION_CREDENTIALS = (Resolve-Path -LiteralPath $CredentialPath).Path
$arguments = @((Join-Path $PSScriptRoot "migrate-room-schema.py"), "--project", $Project)
if ($Apply) {
    $arguments += "--apply"
}

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Room schema migration failed with exit code $LASTEXITCODE"
}
