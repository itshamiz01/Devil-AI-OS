# AUTONOMUS P-01 — environment validation (Windows).
# UNVERIFIED ON WINDOWS: written to the documented toolchain contract
# (P-00 Technology Validation); not yet executed on the target machine.
#Requires -Version 5.1
$ErrorActionPreference = "Continue"

function Check-Tool($Name, $Command, $VersionArg) {
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        Write-Host "[MISSING] $Name ($Command not found)" -ForegroundColor Red
        return $false
    }
    $version = & $Command $VersionArg 2>$null | Select-Object -First 1
    Write-Host "[OK]      $Name : $version" -ForegroundColor Green
    return $true
}

Write-Host "=== AUTONOMUS environment validation ==="
$ok = $true
$ok = (Check-Tool "Python" "python" "--version") -and $ok
$ok = (Check-Tool "Node.js" "node" "--version") -and $ok
$ok = (Check-Tool "Git" "git" "--version") -and $ok
$ok = (Check-Tool "Rust (Tauri, P-11 shell)" "rustc" "--version") -and $ok
$ok = (Check-Tool "Ollama (optional in P-01)" "ollama" "--version") -and $ok

$os = Get-CimInstance Win32_OperatingSystem
Write-Host ("OS: {0} (build {1})" -f $os.Caption, $os.BuildNumber)
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
if ($gpu) { Write-Host ("GPU: {0} ({1:N0} MB VRAM)" -f $gpu.Name, ($gpu.AdapterRAM / 1MB)) }
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Write-Host ("CPU: {0} ({1} cores)" -f $cpu.Name, $cpu.NumberOfCores)
Write-Host ("RAM: {0:N1} GB total" -f ($os.TotalVisibleMemorySize / 1MB))
$drive = Get-PSDrive C
Write-Host ("C: free: {0:N1} GB" -f ($drive.Free / 1GB))

if ($ok) { Write-Host "Core toolchain present."; exit 0 } else { Write-Host "Missing tools listed above."; exit 1 }
