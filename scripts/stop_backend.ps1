param([switch]$Force)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$pidFile = Join-Path $root 'data/backend.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host 'No PID file found. If the backend is running in a console, use Ctrl+C for graceful shutdown.'
    exit 0
}
$backendPid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
if ($Force) {
    Write-Warning 'Forced termination requested. This is not graceful shutdown.'
    Stop-Process -Id $backendPid -Force
} else {
    Write-Host "Backend PID $backendPid. Use Ctrl+C in the backend console for graceful shutdown. Re-run with -Force only for emergency termination."
}
