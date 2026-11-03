<#
.SYNOPSIS
Validate the local AUTONOMUS backend development environment.
.DESCRIPTION
Read-only check of Python, required backend packages, and configuration validity.
Installs nothing.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
if (-not (Test-Path -LiteralPath $backend)) {
    throw "backend folder not found at $backend"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'python not found on PATH. Install Python 3.13 or newer, then re-run.'
}
Set-Location -LiteralPath $backend
& python --version
if ($LASTEXITCODE -ne 0) { throw 'python --version failed.' }

$pyCode = @'
import importlib.metadata as m

required = [
    "fastapi", "uvicorn", "sqlalchemy", "alembic",
    "pydantic", "pydantic-settings", "aiosqlite", "greenlet",
    "psutil", "argon2-cffi",
]
missing = []
for name in required:
    try:
        print(f"{name}=={m.version(name)}")
    except m.PackageNotFoundError:
        missing.append(name)

if missing:
    raise SystemExit(
        "Missing packages: " + ", ".join(missing)
        + "\nInstall them with: python -m pip install -r requirements.txt"
    )

from app.core.config import Settings

settings = Settings()
print(f"Config valid. Host: {settings.host} Port: {settings.port}")
print(f"External execution: {settings.external_execution_enabled}")
print(f"Financial execution: {settings.financial_execution_enabled}")
print(f"Cloud AI: {settings.cloud_ai_enabled}")
'@

$pyCode | & python -
if ($LASTEXITCODE -ne 0) {
    throw 'Environment validation failed. See the messages above.'
}
Write-Host 'Environment validation passed.' -ForegroundColor Green
