# AUTONOMUS P-01 — development startup (Windows), with auto-reload.
# UNVERIFIED ON WINDOWS: not yet executed on the target machine.
#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "backend")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
}

if (-not $env:AUTONOMUS_ADMIN_PASSWORD -and -not $env:AUTONOMUS_DEV_TOKEN) {
    Write-Warning "Neither AUTONOMUS_ADMIN_PASSWORD nor AUTONOMUS_DEV_TOKEN is set: the API will run LOCKED (all protected endpoints reject requests). Set one before starting for real use."
}

$Port = if ($env:AUTONOMUS_PORT) { $env:AUTONOMUS_PORT } else { "8000" }
Write-Host "Starting AUTONOMUS backend (dev, reload) on http://127.0.0.1:$Port"
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
