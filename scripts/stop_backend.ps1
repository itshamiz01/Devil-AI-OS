# AUTONOMUS P-01 — stop the backend gracefully (Windows).
# UNVERIFIED ON WINDOWS: not yet executed on the target machine.
# Sends a normal process close so uvicorn/FastAPI lifespan shutdown runs
# (stop accepting tasks -> finish bounded wait -> close DB -> flush logs).
#Requires -Version 5.1
$ErrorActionPreference = "Continue"
$Port = if ($env:AUTONOMUS_PORT) { $env:AUTONOMUS_PORT } else { "8000" }

$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
    Write-Host "No AUTONOMUS backend listening on port $Port."
    exit 0
}
$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pidValue in $pids) {
    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Requesting graceful shutdown of PID $pidValue ($($proc.ProcessName))..."
        # CloseMainWindow/Stop-Process without -Force lets the process run its shutdown path.
        Stop-Process -Id $pidValue
        try { Wait-Process -Id $pidValue -Timeout 15 -ErrorAction Stop; Write-Host "Stopped." }
        catch { Write-Warning "Process $pidValue did not stop within 15s. It has NOT been force-killed; investigate before using -Force." }
    }
}
