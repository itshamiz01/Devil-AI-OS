# AUTONOMUS P-01 — start the Core OS backend (Windows).
# UNVERIFIED ON WINDOWS: not yet executed on the target machine.
# Binds to loopback by default (AUTONOMUS_HOST / config default 127.0.0.1).
#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "backend")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
}

$Port = if ($env:AUTONOMUS_PORT) { $env:AUTONOMUS_PORT } else { "8000" }
Write-Host "Starting AUTONOMUS backend on http://127.0.0.1:$Port (Ctrl+C for graceful shutdown)"
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $Port
