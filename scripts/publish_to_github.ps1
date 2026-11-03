<#
.SYNOPSIS
One-command Windows publisher for AUTONOMUS work packages.

.DESCRIPTION
Finds an AUTONOMUS package ZIP, clones or reuses your local repo, backs up files
that will be overwritten, extracts the package safely, refuses to stage secrets
or runtime data, optionally runs backend tests, then commits and pushes.

Authentication is handled by your own Git Credential Manager / browser.
This script never asks for, stores, or transmits a password or token.

.PARAMETER PackagePath
Path to the package ZIP. If omitted, the newest AUTONOMUS_*.zip found in
Downloads, Desktop, the current folder, or this script's folder is used.

.PARAMETER RepoDir
Local repository folder. Created by cloning if it does not exist.

.PARAMETER RepoUrl
GitHub repository URL used only when cloning or when origin is missing.

.PARAMETER Branch
Branch to push. Default: main.

.PARAMETER CommitMessage
Commit message. Default describes the P-00 + P-01 delivery.

.PARAMETER RunTests
Run "python -m pytest -q" in backend before committing. Aborts on failure.

.PARAMETER DryRun
Show what would happen without extracting, committing, or pushing.

.PARAMETER NoPush
Commit locally but do not push.

.EXAMPLE
.\publish_to_github.ps1

.EXAMPLE
.\publish_to_github.ps1 -PackagePath "$env:USERPROFILE\Downloads\AUTONOMUS_P01_conditional_backend.zip" -RunTests

.EXAMPLE
.\publish_to_github.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$PackagePath,
    [string]$RepoDir = (Join-Path $env:USERPROFILE 'Devil-AI-OS'),
    [string]$RepoUrl = 'https://github.com/itshamiz01/Devil-AI-OS.git',
    [string]$Branch = 'main',
    [string]$CommitMessage = 'Add AUTONOMUS P-00 foundation and conditional P-01 core backend',
    [switch]$RunTests,
    [switch]$DryRun,
    [switch]$NoPush
)

$ErrorActionPreference = 'Stop'

# Paths that are always published when present in the package.
$PublishPaths = @('README.md', 'LICENSE', '.gitignore', '.env.example', 'backend', 'config', 'docs', 'scripts', 'shared')

# Use the platform directory separator so path guards cannot be bypassed.
$Sep = [System.IO.Path]::DirectorySeparatorChar

# Never publish these, even if a package contains them.
$BlockedPattern = '(^|\\|/)(data|logs|backups|node_modules|\.venv|venv|__pycache__|\.pytest_cache|\.git|models|secrets|credentials|browser-profiles|browser_profiles)(\\|/|$)'
$BlockedFilePattern = '(?i)(^\.env$|^\.env\.(?!example$).+|\.pem$|\.key$|\.p12$|\.pfx$|\.db$|\.sqlite$|\.sqlite3$|\.gguf$|\.safetensors$|\.log$|\.bak$)'
$SecretContentPattern = '(-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})'

function Write-Step { param([string]$Text) Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok { param([string]$Text) Write-Host "    $Text" -ForegroundColor Green }
function Write-Warn2 { param([string]$Text) Write-Host "    $Text" -ForegroundColor Yellow }

function Invoke-Git {
    param([string[]]$GitArgs, [switch]$AllowFailure)
    $output = & git @GitArgs 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "git $($GitArgs -join ' ') failed (exit $code):`n$($output -join "`n")"
    }
    return [pscustomobject]@{ Code = $code; Output = ($output -join "`n").Trim() }
}

if ($env:OS -ne 'Windows_NT') {
    throw 'This publisher must run on Windows.'
}

# ---------------------------------------------------------------- prerequisites
Write-Step 'Checking prerequisites'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is not installed or not on PATH. Install Git for Windows, then re-run.'
}
Write-Ok "git: $((Invoke-Git @('version')).Output)"

$nameCheck = Invoke-Git @('config', 'user.name') -AllowFailure
$emailCheck = Invoke-Git @('config', 'user.email') -AllowFailure
if (-not $nameCheck.Output -or -not $emailCheck.Output) {
    throw @"
Git identity is not configured. Run these once, then re-run this script:
  git config --global user.name  "Your Name"
  git config --global user.email "your-email@example.com"
"@
}
Write-Ok "identity: $($nameCheck.Output) <$($emailCheck.Output)>"

# ---------------------------------------------------------------- locate package
Write-Step 'Locating package'
if (-not $PackagePath) {
    $searchDirs = @()
    if ($env:USERPROFILE) {
        $searchDirs += (Join-Path $env:USERPROFILE 'Downloads')
        $searchDirs += (Join-Path $env:USERPROFILE 'Desktop')
    }
    $searchDirs += (Get-Location).Path
    if ($PSScriptRoot) { $searchDirs += $PSScriptRoot }
    $candidates = @()
    foreach ($dir in ($searchDirs | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $dir) {
            $candidates += Get-ChildItem -LiteralPath $dir -Filter 'AUTONOMUS_*.zip' -File -ErrorAction SilentlyContinue
        }
    }
    if (-not $candidates) {
        throw 'No AUTONOMUS_*.zip found. Download the package, or pass -PackagePath "C:\path\to\package.zip".'
    }
    $chosen = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $PackagePath = $chosen.FullName
}
if (-not (Test-Path -LiteralPath $PackagePath)) {
    throw "Package not found: $PackagePath"
}
$PackagePath = (Resolve-Path -LiteralPath $PackagePath).Path
Write-Ok "package: $PackagePath"
Write-Ok ("size: {0:N0} bytes, modified {1}" -f (Get-Item -LiteralPath $PackagePath).Length, (Get-Item -LiteralPath $PackagePath).LastWriteTime)

# ---------------------------------------------------------------- inspect package
Write-Step 'Inspecting package contents'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($PackagePath)
$toExtract = @()
$skipped = @()
try {
    foreach ($entry in $zip.Entries) {
        if ([string]::IsNullOrEmpty($entry.Name)) { continue }
        $rel = $entry.FullName.Replace('/', [string]$Sep)
        if ($rel -match '\.\.' -or [System.IO.Path]::IsPathRooted($rel)) {
            throw "Unsafe path in package (possible zip-slip): $($entry.FullName)"
        }
        if ($rel -match $BlockedPattern -or $entry.Name -match $BlockedFilePattern) {
            $skipped += $rel
            continue
        }
        $toExtract += $entry.FullName
    }
}
finally {
    $zip.Dispose()
}
Write-Ok "files to publish: $($toExtract.Count)"
if ($skipped.Count -gt 0) {
    Write-Warn2 "blocked runtime/secret files skipped: $($skipped.Count)"
    $skipped | Select-Object -First 10 | ForEach-Object { Write-Host "      skip $_" }
}
if ($toExtract.Count -eq 0) { throw 'Package contains no publishable files.' }

# ---------------------------------------------------------------- repository
Write-Step 'Preparing local repository'
if (-not (Test-Path -LiteralPath $RepoDir)) {
    if ($DryRun) {
        Write-Warn2 "[dry-run] would clone $RepoUrl into $RepoDir"
    }
    else {
        $parent = Split-Path -Parent $RepoDir
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Invoke-Git @('clone', $RepoUrl, $RepoDir) | Out-Null
        Write-Ok "cloned into $RepoDir"
    }
}
else {
    Write-Ok "using existing folder: $RepoDir"
}

if ($DryRun -and -not (Test-Path -LiteralPath $RepoDir)) {
    Write-Step 'Dry run summary'
    Write-Ok "would extract $($toExtract.Count) files, commit, and push to $Branch"
    Write-Ok 'no changes were made'
    return
}

Push-Location -LiteralPath $RepoDir
try {
    if (-not (Test-Path -LiteralPath (Join-Path $RepoDir '.git'))) {
        throw "$RepoDir exists but is not a Git repository. Choose an empty path with -RepoDir."
    }

    $remoteCheck = Invoke-Git @('remote', 'get-url', 'origin') -AllowFailure
    if ($remoteCheck.Code -ne 0) {
        if ($DryRun) { Write-Warn2 "[dry-run] would add origin $RepoUrl" }
        else {
            Invoke-Git @('remote', 'add', 'origin', $RepoUrl) | Out-Null
            Write-Ok "added origin $RepoUrl"
        }
    }
    else {
        Write-Ok "origin: $($remoteCheck.Output)"
    }

    $dirty = Invoke-Git @('status', '--porcelain')
    if ($dirty.Output) {
        Write-Warn2 'working tree already has uncommitted changes; they will be included only if under published paths'
    }

    $currentBranch = (Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD') -AllowFailure).Output
    if ($currentBranch -and $currentBranch -ne $Branch -and $currentBranch -ne 'HEAD') {
        Write-Warn2 "current branch is '$currentBranch' but target is '$Branch'"
        if (-not $DryRun) {
            Invoke-Git @('checkout', $Branch) | Out-Null
            Write-Ok "switched to $Branch"
        }
    }

    # ------------------------------------------------------------ backup
    if (-not $DryRun) {
        Write-Step 'Backing up files that will be overwritten'
        $backupRoot = Join-Path $RepoDir 'backups'
        New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backupZip = Join-Path $backupRoot "pre-publish-$stamp.zip"
        $existing = @()
        foreach ($p in $PublishPaths) {
            $full = Join-Path $RepoDir $p
            if (Test-Path -LiteralPath $full) { $existing += $p }
        }
        if ($existing.Count -gt 0) {
            # Compress-Archive cannot read hidden dotfiles, so build the archive directly.
            Add-Type -AssemblyName System.IO.Compression | Out-Null
            $rootLen = ([System.IO.Path]::GetFullPath($RepoDir).TrimEnd($Sep)).Length + 1
            $fs = [System.IO.File]::Open($backupZip, [System.IO.FileMode]::Create)
            $archive = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create)
            $backedUp = 0
            try {
                foreach ($p in $existing) {
                    $full = Join-Path $RepoDir $p
                    if (Test-Path -LiteralPath $full -PathType Container) {
                        foreach ($f in (Get-ChildItem -LiteralPath $full -Recurse -File -Force)) {
                            $rel = $f.FullName.Substring($rootLen)
                            if ($rel -match $BlockedPattern) { continue }
                            $entryName = $rel.Replace([string]$Sep, '/')
                            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $f.FullName, $entryName) | Out-Null
                            $backedUp++
                        }
                    }
                    else {
                        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $full, $p.Replace([string]$Sep, '/')) | Out-Null
                        $backedUp++
                    }
                }
            }
            finally {
                $archive.Dispose()
                $fs.Dispose()
            }
            Write-Ok "backup: $backupZip ($backedUp files, gitignored)"
        }
        else {
            Write-Ok 'nothing to back up (fresh repo)'
        }
    }

    # ------------------------------------------------------------ extract
    Write-Step 'Extracting package'
    if ($DryRun) {
        $toExtract | Select-Object -First 15 | ForEach-Object { Write-Host "      would write $_" }
        if ($toExtract.Count -gt 15) { Write-Host "      ... and $($toExtract.Count - 15) more" }
    }
    else {
        $repoRootFull = [System.IO.Path]::GetFullPath($RepoDir).TrimEnd($Sep) + $Sep
        $zip = [System.IO.Compression.ZipFile]::OpenRead($PackagePath)
        try {
            $entryMap = @{}
            foreach ($e in $zip.Entries) { $entryMap[$e.FullName] = $e }
            foreach ($name in $toExtract) {
                $rel = $name.Replace('/', [string]$Sep)
                $dest = [System.IO.Path]::GetFullPath((Join-Path $RepoDir $rel))
                if (-not $dest.StartsWith($repoRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw "Refusing to write outside repo: $name"
                }
                if (-not $entryMap.ContainsKey($name)) {
                    throw "Package entry disappeared between inspection and extraction: $name"
                }
                $destDir = Split-Path -Parent $dest
                if (-not (Test-Path -LiteralPath $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entryMap[$name], $dest, $true)
            }
        }
        finally {
            $zip.Dispose()
        }
        Write-Ok "extracted $($toExtract.Count) files"
    }

    # ------------------------------------------------------------ tests
    if ($RunTests) {
        Write-Step 'Running backend tests'
        if ($DryRun) {
            Write-Warn2 '[dry-run] tests skipped'
        }
        elseif (-not (Get-Command python -ErrorAction SilentlyContinue)) {
            throw 'python not found on PATH. Install Python or omit -RunTests.'
        }
        else {
            $backendDir = Join-Path $RepoDir 'backend'
            if (-not (Test-Path -LiteralPath $backendDir)) { throw 'backend folder missing; cannot run tests.' }
            Push-Location -LiteralPath $backendDir
            try {
                & python -m pytest -q
                if ($LASTEXITCODE -ne 0) { throw "Backend tests failed (exit $LASTEXITCODE). Nothing was committed." }
            }
            finally { Pop-Location }
            Write-Ok 'backend tests passed'
        }
    }

    # ------------------------------------------------------------ stage
    Write-Step 'Staging published paths'
    $stageList = @()
    foreach ($p in $PublishPaths) {
        if (Test-Path -LiteralPath (Join-Path $RepoDir $p)) { $stageList += $p }
    }
    if ($stageList.Count -eq 0) { throw 'No published paths present after extraction.' }
    Write-Ok "paths: $($stageList -join ', ')"

    if (-not $DryRun) {
        Invoke-Git (@('add', '--') + $stageList) | Out-Null

        $staged = (Invoke-Git @('diff', '--cached', '--name-only')).Output
        if (-not $staged) {
            Write-Warn2 'Nothing new to commit. Repository already matches this package.'
            return
        }
        $stagedFiles = $staged -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }

        # ------------------------------------------------------------ safety gate
        Write-Step 'Checking staged files for secrets and runtime data'
        $offenders = @()
        foreach ($f in $stagedFiles) {
            $norm = $f.Replace('/', [string]$Sep)
            if ($norm -match $BlockedPattern -or (Split-Path -Leaf $norm) -match $BlockedFilePattern) {
                $offenders += $f
            }
        }
        if ($offenders.Count -gt 0) {
            Invoke-Git @('reset') | Out-Null
            throw "Refusing to commit blocked paths:`n  $($offenders -join "`n  ")"
        }
        foreach ($f in $stagedFiles) {
            $full = Join-Path $RepoDir $f
            if (Test-Path -LiteralPath $full -PathType Leaf) {
                $item = Get-Item -LiteralPath $full -Force
                if ($item.Length -lt 2MB) {
                    $text = Get-Content -LiteralPath $full -Raw -Force -ErrorAction SilentlyContinue
                    if ($text -and $text -match $SecretContentPattern) {
                        Invoke-Git @('reset') | Out-Null
                        throw "Possible credential detected in '$f'. Nothing was committed. Remove it and re-run."
                    }
                }
            }
        }
        Write-Ok "$($stagedFiles.Count) files passed the safety gate"

        # ------------------------------------------------------------ commit
        Write-Step 'Committing'
        Invoke-Git @('commit', '-m', $CommitMessage) | Out-Null
        $commit = (Invoke-Git @('rev-parse', '--short', 'HEAD')).Output
        Write-Ok "commit $commit"

        # ------------------------------------------------------------ push
        if ($NoPush) {
            Write-Warn2 'NoPush specified; commit kept locally.'
        }
        else {
            Write-Step "Pushing to origin/$Branch"
            Write-Host '    Git may open a browser or credential prompt. Sign in with your own GitHub account.'
            $push = Invoke-Git @('push', 'origin', $Branch) -AllowFailure
            if ($push.Code -ne 0) {
                Write-Warn2 "Push failed:`n$($push.Output)"
                throw @"
Push did not complete. Your commit is safe locally.
Most common fix (remote has newer commits):
  git pull --rebase origin $Branch
  git push origin $Branch
If authentication failed, sign in again via Git Credential Manager. Never use --force.
"@
            }
            Write-Ok "pushed to origin/$Branch"
            Write-Host ''
            Write-Host "Published: https://github.com/itshamiz01/Devil-AI-OS/tree/$Branch" -ForegroundColor Green
        }
    }
    else {
        Write-Step 'Dry run summary'
        Write-Ok "would stage: $($stageList -join ', ')"
        Write-Ok "would commit: $CommitMessage"
        if ($NoPush) { Write-Ok 'would not push (-NoPush)' } else { Write-Ok "would push to origin/$Branch" }
        Write-Ok 'no changes were made'
    }
}
finally {
    Pop-Location
}
