param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$env:AUTONOMUS_ENVIRONMENT = 'development'
& (Join-Path $PSScriptRoot 'start_backend.ps1') -Port $Port
