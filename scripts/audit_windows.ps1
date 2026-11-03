<#
.SYNOPSIS
Read-only Windows host/tool audit for AUTONOMUS P-00.
.DESCRIPTION
Collects hardware and development-tool facts. Does not install software,
pull models, run inference, read credentials or change system settings.
The only write is the JSON report. Existing reports are not overwritten
unless the owner explicitly supplies -Force.
Run from an ordinary PowerShell session after reviewing this script.
#>
[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'docs\reports\WINDOWS_HOST_AUDIT.json'),
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'This audit must run on the target Windows computer.'
}
$OutputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromFileSystemPath($OutputPath)
if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "Report already exists: $OutputPath. Choose a new path or explicitly use -Force."
}

$script:Warnings = @()
function Read-Section {
    param([string]$Label, [scriptblock]$Query)
    try { return & $Query }
    catch {
        $script:Warnings += "$Label unavailable: $($_.Exception.Message)"
        return $null
    }
}
function Get-ToolVersion {
    param([string]$Name, [string[]]$VersionArgs = @('--version'))
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return [ordered]@{ available = $false; version = $null }
    }
    try {
        $output = & $command.Source @VersionArgs 2>&1
        $text = (($output | ForEach-Object { $_.ToString() }) -join ' ').Trim()
        return [ordered]@{ available = $true; version = $text }
    }
    catch {
        $script:Warnings += "$Name version check failed: $($_.Exception.Message)"
        return [ordered]@{ available = $true; version = $null }
    }
}

$osInfo = Read-Section 'Operating system' {
    Get-CimInstance Win32_OperatingSystem |
        Select-Object Caption, Version, BuildNumber, OSArchitecture,
            TotalVisibleMemorySize, FreePhysicalMemory
}
$cpuInfo = Read-Section 'CPU' {
    @(Get-CimInstance Win32_Processor |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed)
}
$gpuInfo = Read-Section 'GPU' {
    @(Get-CimInstance Win32_VideoController |
        Select-Object Name, DriverVersion, AdapterRAM, VideoModeDescription)
}
$diskInfo = Read-Section 'Logical disks' {
    @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
        Select-Object DeviceID, FileSystem, Size, FreeSpace)
}
$physicalDiskInfo = Read-Section 'Physical disks' {
    @(Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, Size)
}
$tools = [ordered]@{}
$tools['PowerShell'] = [ordered]@{ available = $true; version = $PSVersionTable.PSVersion.ToString() }
$tools['Python'] = Get-ToolVersion 'python'
$tools['Python launcher'] = Get-ToolVersion 'py'
$tools['Node.js'] = Get-ToolVersion 'node'
$tools['npm'] = Get-ToolVersion 'npm.cmd'
$tools['Git'] = Get-ToolVersion 'git' @('version')
$tools['Rust compiler'] = Get-ToolVersion 'rustc'
$tools['Cargo'] = Get-ToolVersion 'cargo'
$tools['rustup'] = Get-ToolVersion 'rustup'
$tools['Ollama'] = Get-ToolVersion 'ollama'

$rustToolchain = Read-Section 'Active Rust toolchain' {
    if (Get-Command rustup -ErrorAction SilentlyContinue) {
        return ((& rustup show active-toolchain 2>&1) -join ' ').Trim()
    }
    return $null
}
$vsBuildTools = Read-Section 'Visual Studio C++ Build Tools' {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { return $null }
    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ([string]::IsNullOrWhiteSpace($installPath)) { return $null }
    $installVersion = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion
    return [ordered]@{ detected = $true; installationVersion = ($installVersion -join ' ').Trim() }
}
$windowsSdk = Read-Section 'Windows SDK' {
    $path = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Microsoft SDKs\Windows\v10.0'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $item = Get-ItemProperty -LiteralPath $path
    return [ordered]@{ productVersion = $item.ProductVersion; installationVersion = $item.InstallationVersion }
}
$webView2 = Read-Section 'WebView2 runtime' {
    $guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    $roots = @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate', 'HKLM:\SOFTWARE\Microsoft\EdgeUpdate', 'HKCU:\SOFTWARE\Microsoft\EdgeUpdate')
    $results = @()
    foreach ($root in $roots) {
        foreach ($kind in @('Clients', 'ClientState')) {
            $path = Join-Path (Join-Path $root $kind) $guid
            if (Test-Path -LiteralPath $path) {
                $item = Get-ItemProperty -LiteralPath $path
                if ($item.pv -and $item.pv -ne '0.0.0.0') {
                    $results += [ordered]@{ registryScope = $root; version = $item.pv }
                }
            }
        }
    }
    return $results
}
$ollamaModels = Read-Section 'Local Ollama model inventory' {
    if (-not $tools['Ollama'].available) { return $null }
    $response = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 3
    return @($response.models | Select-Object name, size,
        @{Name = 'parameterSize'; Expression = { $_.details.parameter_size }},
        @{Name = 'quantization'; Expression = { $_.details.quantization_level }})
}

$report = [ordered]@{
    schemaVersion = 1
    capturedUtc = [DateTime]::UtcNow.ToString('o')
    evidenceType = 'Owner-run Windows inspection; not independently verified by Arena'
    privacyNote = 'Hardware/tool metadata only. No credentials, prompts, documents or wallet data intentionally collected. Review before sharing.'
    operatingSystem = $osInfo
    cpu = $cpuInfo
    gpu = $gpuInfo
    gpuMemoryNote = 'Win32_VideoController.AdapterRAM may be limited or inaccurate for large/shared-memory GPUs. Verify with vendor tools.'
    logicalDisks = $diskInfo
    physicalDisks = $physicalDiskInfo
    tools = $tools
    activeRustToolchain = $rustToolchain
    visualStudioCppBuildTools = $vsBuildTools
    windowsSdk = $windowsSdk
    webView2 = $webView2
    ollamaModels = $ollamaModels
    warnings = $script:Warnings
    notPerformed = @('Installation', 'Model download', 'Inference benchmark', 'Application build', 'Credential inspection', 'Financial operation')
}

$parent = Split-Path -Parent $OutputPath
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent | Out-Null
}
$json = $report | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($OutputPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "Read-only audit saved to $OutputPath"
Write-Host 'Review the report before sharing or committing it. No inference benchmark was performed.'
