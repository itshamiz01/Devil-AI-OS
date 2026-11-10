# AUTONOMUS P-01 — health check (Windows).
# UNVERIFIED ON WINDOWS: not yet executed on the target machine.
# Liveness is unauthenticated; readiness requires a credential
# (AUTONOMUS_DEV_TOKEN or a session token in AUTONOMUS_ACCESS_TOKEN).
#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Port = if ($env:AUTONOMUS_PORT) { $env:AUTONOMUS_PORT } else { "8000" }
$Base = "http://127.0.0.1:$Port/api/v1"

Write-Host "--- Liveness ---"
$live = Invoke-RestMethod -Uri "$Base/health/live" -Method Get
$live.data | Format-List

$token = if ($env:AUTONOMUS_ACCESS_TOKEN) { $env:AUTONOMUS_ACCESS_TOKEN } elseif ($env:AUTONOMUS_DEV_TOKEN) { $env:AUTONOMUS_DEV_TOKEN } else { $null }
if ($token) {
    Write-Host "--- Readiness ---"
    $headers = @{ Authorization = "Bearer $token" }
    try {
        $ready = Invoke-RestMethod -Uri "$Base/health/ready" -Method Get -Headers $headers
        $ready.data | Format-List
    } catch {
        Write-Warning "Readiness check failed or not ready: $($_.Exception.Message)"
        exit 2
    }
} else {
    Write-Warning "No token available (set AUTONOMUS_ACCESS_TOKEN or AUTONOMUS_DEV_TOKEN); readiness check skipped."
}
exit 0
