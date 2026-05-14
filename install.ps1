#Requires -Version 5.1
<#
.SYNOPSIS
  Taskforce Community - native installer for Windows.

.DESCRIPTION
  Installs the Community edition. Default 'binary' mode downloads a prebuilt
  bundle from GitHub Releases (no Python needed). '-FromSource' clones the
  repository and installs via uv.

.EXAMPLE
  irm https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.ps1 | iex

.EXAMPLE
  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/rudi77/pytaskforce/main/install.ps1))) -FromSource
#>
[CmdletBinding()]
param(
    [switch] $FromSource,
    [string] $Version = $env:TASKFORCE_VERSION,
    [string] $InstallHome = $env:TASKFORCE_HOME
)

$ErrorActionPreference = 'Stop'
$Repo = 'rudi77/pytaskforce'
if (-not $Version)     { $Version = 'latest' }
if (-not $InstallHome) { $InstallHome = Join-Path $env:USERPROFILE '.taskforce' }
$BinDir = Join-Path $env:LOCALAPPDATA 'Taskforce\bin'

function Say  ($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn ($m) { Write-Host "warning: $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "error: $m" -ForegroundColor Red; exit 1 }

function Install-Binary {
    $arch = if ([Environment]::Is64BitOperatingSystem) {
        if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
    } else { Die 'unsupported architecture (32-bit)' }
    $asset = "taskforce-community-windows-$arch.zip"
    if ($Version -eq 'latest') {
        $url = "https://github.com/$Repo/releases/latest/download/$asset"
    } else {
        $url = "https://github.com/$Repo/releases/download/v$($Version.TrimStart('v'))/$asset"
    }
    Say "Downloading $asset ..."
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    $zip = Join-Path $tmp $asset
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    } catch {
        Die "no prebuilt bundle for windows-$arch ($Version).`nRetry from source:`n  irm https://raw.githubusercontent.com/$Repo/main/install.ps1 | iex -Args '-FromSource'"
    }
    $bundle = Join-Path $InstallHome 'bundle'
    if (Test-Path $bundle) { Remove-Item -Recurse -Force $bundle }
    New-Item -ItemType Directory -Path $bundle -Force | Out-Null
    Say "Extracting to $bundle ..."
    Expand-Archive -Path $zip -DestinationPath $bundle -Force
    Remove-Item -Recurse -Force $tmp
    # Bundles may unpack into a single top-level folder; flatten if so.
    $exe = Get-ChildItem -Path $bundle -Recurse -Filter 'taskforce.exe' | Select-Object -First 1
    if (-not $exe) { Die "bundle did not contain taskforce.exe" }
    $script:RunTarget = $exe.FullName
    $script:RunArgs = $false
}

function Install-Source {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die 'git is required for -FromSource' }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Say 'Installing uv (Python package manager) ...'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Die 'uv installation failed' }
    $src = Join-Path $InstallHome 'src'
    $ref = if ($Version -eq 'latest') { $null } else { $Version }
    if (Test-Path (Join-Path $src '.git')) {
        Say 'Updating existing checkout ...'
        git -C $src fetch --depth 1 origin ($(if ($ref) { $ref } else { 'HEAD' }))
        git -C $src checkout -f FETCH_HEAD
    } else {
        Say "Cloning $Repo ..."
        if (Test-Path $src) { Remove-Item -Recurse -Force $src }
        if ($ref) {
            git clone --depth 1 --branch $ref "https://github.com/$Repo.git" $src
        } else {
            git clone --depth 1 "https://github.com/$Repo.git" $src
        }
    }
    Say 'Installing dependencies with uv (downloads Python + packages) ...'
    Push-Location $src
    try {
        uv sync --frozen
        Say 'Installing the Chromium browser for the browser tool ...'
        uv run playwright install chromium
        if ((Get-Command corepack -ErrorAction SilentlyContinue) -or (Get-Command pnpm -ErrorAction SilentlyContinue)) {
            Say 'Building the web UI ...'
            try {
                Push-Location (Join-Path $src 'ui')
                corepack enable 2>$null
                pnpm install --frozen-lockfile
                pnpm run build
                Pop-Location
                $uiDst = Join-Path $src 'src\taskforce\api\_ui'
                if (Test-Path $uiDst) { Remove-Item -Recurse -Force $uiDst }
                Copy-Item -Recurse (Join-Path $src 'ui\dist') $uiDst
            } catch {
                Warn 'UI build failed - the web UI will be unavailable (REST API still works)'
            }
        } else {
            Warn 'pnpm/corepack not found - skipping web UI build (REST API still works)'
        }
    } finally {
        Pop-Location
    }
    $script:RunTarget = $src
    $script:RunArgs = $true   # invoke via 'uv run --project <src> taskforce'
}

function Set-EnvFile {
    New-Item -ItemType Directory -Path $InstallHome -Force | Out-Null
    $envFile = Join-Path $InstallHome '.env'
    if (Test-Path $envFile) { Say "Keeping existing configuration at $envFile"; return }
    $key = Read-Host 'Enter your OpenAI API key (leave blank to configure later)'
    $lines = @('# Taskforce configuration - edit any time, then restart ''taskforce up''.')
    if ($key) { $lines += "OPENAI_API_KEY=$key" } else { $lines += '# OPENAI_API_KEY=sk-...' }
    $lines += '# Other providers / tools - see .env.example in the repository.'
    Set-Content -Path $envFile -Value $lines -Encoding UTF8
    Say "Wrote configuration to $envFile"
}

function Write-Launcher {
    $appDir = Join-Path $InstallHome 'app'
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    $launcher = Join-Path $BinDir 'taskforce.cmd'
    $envFile = Join-Path $InstallHome '.env'
    if ($script:RunArgs) {
        $invoke = "uv run --project `"$script:RunTarget`" taskforce %*"
    } else {
        $invoke = "`"$script:RunTarget`" %*"
    }
    $cmd = @(
        '@echo off',
        'setlocal',
        "if exist `"$envFile`" (for /f `"usebackq tokens=1,* delims==`" %%A in (`"$envFile`") do (if not `"%%A`"==`"`" if not `"%%A:~0,1`"==`"#`" set `"%%A=%%B`"))",
        $invoke
    )
    Set-Content -Path $launcher -Value $cmd -Encoding ASCII
    Say "Wrote launcher $launcher"
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -notlike "*$BinDir*") {
        [Environment]::SetEnvironmentVariable('Path', "$userPath;$BinDir", 'User')
        Say "Added $BinDir to your PATH (restart the terminal to pick it up)."
    }
}

Say "Installing Taskforce Community ($(if ($FromSource) {'source'} else {'binary'}) mode) ..."
if ($FromSource) { Install-Source } else { Install-Binary }
Set-EnvFile
Write-Launcher
Write-Host ''
Say 'Taskforce Community installed.'
Write-Host ''
Write-Host '  Next steps:'
Write-Host '    taskforce up        # start Taskforce and open the web UI'
Write-Host ''
