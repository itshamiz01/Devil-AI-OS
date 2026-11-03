param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location (Join-Path $root 'backend')
$env:AUTONOMUS_HOST = '127.0.0.1'
$env:AUTONOMUS_PORT = "$Port"
python -m app.cli serve
