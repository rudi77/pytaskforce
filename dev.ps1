# dev.ps1 - one-shot dev launcher for pytaskforce + UI (enterprise mode)
#
# Usage:
#   .\dev.ps1                  # backend (8070) + UI (5173) in this terminal, prefixed logs
#   .\dev.ps1 -Split           # backend + UI in two new terminal windows (separate Ctrl+C)
#   .\dev.ps1 -Backend         # backend only, foreground in this terminal
#   .\dev.ps1 -Frontend        # UI only, foreground in this terminal
#   .\dev.ps1 -Install         # force reinstall enterprise plugin + UI deps, then start
#   .\dev.ps1 -Migrate         # force-run alembic migrations + bootstrap, then start
#   .\dev.ps1 -SkipMigrate     # don't run alembic on startup (faster cold start)
#   .\dev.ps1 -Build           # production build of UI (no dev server), then exit
#   .\dev.ps1 -Port 8080       # override backend port (also re-points UI proxy)
#   .\dev.ps1 -ForceVite       # always wipe Vite dep cache + start with --force
#
# Stale-chunk protection:
#   Before starting the UI, the script hashes
#       ui/node_modules/@taskforce/enterprise-ui/dist/index.js (+ index.css)
#   and compares with ui/.dev-fingerprint. If the dist changed since the last
#   run, ui/node_modules/.vite is wiped and Vite is started with --force, so
#   the browser stops requesting old chunk hashes (e.g. CreateUserPage-XXX.js
#   404 / "Page update required").
#
# Stops processes cleanly on Ctrl+C (single-terminal mode).

[CmdletBinding()]
param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$Split,
    [switch]$Install,
    [switch]$Migrate,
    [switch]$SkipMigrate,
    [switch]$Build,
    [switch]$ForceVite,
    [int]$Port = 8070,
    [string]$Host_ = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$EnterpriseRoot = Join-Path (Split-Path $RepoRoot -Parent) "taskforce-enterprise"
$Venv = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvActivate = Join-Path $Venv "Scripts\Activate.ps1"
$VenvTaskforce = Join-Path $Venv "Scripts\taskforce.exe"
$UiDir = Join-Path $RepoRoot "ui"
$ViteCacheDir = Join-Path $UiDir "node_modules\.vite"
$EnterpriseUiDist = Join-Path $UiDir "node_modules\@taskforce\enterprise-ui\dist"
$ViteFingerprintFile = Join-Path $UiDir ".dev-fingerprint"

function Write-Step  { param($msg) Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2 { param($msg) Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "    $msg" -ForegroundColor Red }

# ---------------------------------------------------------------- pre-flight
function Test-Venv {
    if (-not (Test-Path $VenvPython)) {
        Write-Err "no .venv found at $Venv. Run 'uv sync' first."
        exit 1
    }
}

function Test-EnterprisePlugin {
    $code = @"
import importlib.metadata as md
eps = list(md.entry_points(group='taskforce.plugins'))
names = [e.name for e in eps]
print('OK' if 'enterprise' in names else 'MISSING')
"@
    $result = & $VenvPython -c $code 2>&1
    return ($result -match 'OK')
}

function Install-EnterprisePlugin {
    if (-not (Test-Path $EnterpriseRoot)) {
        Write-Err "taskforce-enterprise repo not found at $EnterpriseRoot"
        Write-Err "Clone it next to pytaskforce, or set `$EnterpriseRoot in this script."
        exit 1
    }
    Write-Step "installing taskforce-enterprise (editable) into .venv"
    & uv pip install -e $EnterpriseRoot
    if ($LASTEXITCODE -ne 0) {
        Write-Err "uv pip install failed (exit $LASTEXITCODE)"
        exit 1
    }
    Write-Ok "enterprise plugin installed"
}

function Test-UiDeps {
    return (Test-Path (Join-Path $UiDir "node_modules"))
}

function Invoke-EnterpriseBootstrap {
    # Runs `taskforce-enterprise admin bootstrap` from the enterprise repo root
    # with .env injected. Idempotent: applies any pending alembic migrations
    # and creates the bootstrap tenant/admin if missing.
    Write-Step "applying alembic migrations + bootstrap (idempotent)"
    $bootstrapExe = Join-Path $Venv "Scripts\taskforce-enterprise.exe"
    if (-not (Test-Path $bootstrapExe)) {
        Write-Warn2 "taskforce-enterprise.exe missing — skipping migrations"
        return
    }
    $envFile = Join-Path $RepoRoot ".env"
    $script = @"
import os, subprocess, sys
from pathlib import Path
envfile = Path(r'$envFile')
if envfile.exists():
    for line in envfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")
r = subprocess.run(
    [r'$bootstrapExe', 'admin', 'bootstrap'],
    env=os.environ,
    cwd=r'$EnterpriseRoot',
)
sys.exit(r.returncode)
"@
    & $VenvPython -c $script
    if ($LASTEXITCODE -ne 0) {
        Write-Err "bootstrap failed (exit $LASTEXITCODE) — start anyway, but the DB schema may be out of sync"
    } else {
        Write-Ok "DB schema up-to-date"
    }
}

function Install-UiDeps {
    Write-Step "installing UI dependencies (pnpm install)"
    Push-Location $UiDir
    try {
        & pnpm install
        if ($LASTEXITCODE -ne 0) { throw "pnpm install failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    Write-Ok "UI deps ready"
}

# ---------------------------------------- stale-chunk protection (Vite cache)
function Get-EnterpriseUiFingerprint {
    # SHA256(dist/index.js) + SHA256(dist/index.css). When enterprise-ui is
    # rebuilt, code-split chunk hashes change -> index.js content changes ->
    # fingerprint changes. Returns $null when dist isn't there yet.
    $indexJs  = Join-Path $EnterpriseUiDist "index.js"
    $indexCss = Join-Path $EnterpriseUiDist "index.css"
    if (-not (Test-Path $indexJs)) { return $null }
    $parts = @((Get-FileHash -Algorithm SHA256 -Path $indexJs).Hash)
    if (Test-Path $indexCss) {
        $parts += (Get-FileHash -Algorithm SHA256 -Path $indexCss).Hash
    }
    return ($parts -join ":")
}

function Sync-ViteCacheForEnterpriseUi {
    # Returns $true if Vite should be started with --force (cache was wiped).
    if ($ForceVite) {
        if (Test-Path $ViteCacheDir) {
            Write-Step "(-ForceVite) clearing Vite dep cache"
            Remove-Item -Recurse -Force $ViteCacheDir
        }
        $current = Get-EnterpriseUiFingerprint
        if ($current) {
            Set-Content -Path $ViteFingerprintFile -Value $current -NoNewline -Encoding ascii
        }
        return $true
    }
    $current = Get-EnterpriseUiFingerprint
    if (-not $current) {
        Write-Warn2 "enterprise-ui dist not found at $EnterpriseUiDist — skipping Vite cache check"
        return $false
    }
    $previous = ""
    if (Test-Path $ViteFingerprintFile) {
        $previous = (Get-Content $ViteFingerprintFile -Raw -ErrorAction SilentlyContinue).Trim()
    }
    if ($current -eq $previous -and (Test-Path $ViteCacheDir)) {
        Write-Ok "Vite cache: enterprise-ui unchanged"
        return $false
    }
    if ($previous -and $current -ne $previous) {
        Write-Step "enterprise-ui dist changed since last run — clearing Vite dep cache"
    } elseif (-not (Test-Path $ViteCacheDir)) {
        Write-Step "no Vite dep cache yet — will optimize on start"
    } else {
        Write-Step "no fingerprint stored — clearing Vite dep cache"
    }
    if (Test-Path $ViteCacheDir) {
        Remove-Item -Recurse -Force $ViteCacheDir
    }
    Set-Content -Path $ViteFingerprintFile -Value $current -NoNewline -Encoding ascii
    Write-Ok "Vite will re-optimize deps (fingerprint refreshed)"
    return $true
}

# ---------------------------------------------------------------- modes
function Invoke-Build {
    Write-Step "building UI for production"
    Push-Location $UiDir
    try {
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw "pnpm build failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    Write-Ok "UI built -> $UiDir\dist"
}

function Start-BackendForeground {
    $backendUrl = "http://${Host_}:${Port}"
    $env:TASKFORCE_API_URL = $backendUrl
    if (-not (Test-Path $VenvTaskforce)) {
        Write-Err "taskforce.exe not found at $VenvTaskforce — run 'uv sync' first"
        exit 1
    }
    Write-Step "starting backend on $backendUrl  (taskforce serve --reload)"
    Write-Host ""
    & $VenvTaskforce serve --host $Host_ --port $Port --reload
}

function Start-FrontendForeground {
    $backendUrl = "http://${Host_}:${Port}"
    $env:TASKFORCE_API_URL = $backendUrl
    $needForce = Sync-ViteCacheForEnterpriseUi
    Write-Step "starting UI on http://localhost:5173  (pnpm dev)"
    Write-Host ""
    Push-Location $UiDir
    try {
        if ($needForce) {
            & pnpm dev -- --force
        } else {
            & pnpm dev
        }
    } finally {
        Pop-Location
    }
}

function Start-Split {
    # Spawn two new terminal windows: one for backend, one for frontend.
    # Each window is its own process tree -> independent logs, independent Ctrl+C.
    $shellPath = (Get-Process -Id $PID).Path
    $scriptPath = $PSCommandPath
    $passthru = @()
    if ($Port -ne 8070)         { $passthru += @("-Port", "$Port") }
    if ($Host_ -ne "127.0.0.1") { $passthru += @("-Host_", $Host_) }
    if ($SkipMigrate)           { $passthru += "-SkipMigrate" }
    if ($Migrate)               { $passthru += "-Migrate" }
    if ($Install)               { $passthru += "-Install" }
    if ($ForceVite)             { $passthru += "-ForceVite" }

    Write-Step "spawning backend in a new terminal"
    Start-Process -FilePath $shellPath `
        -ArgumentList (@("-NoExit", "-File", $scriptPath, "-Backend") + $passthru) `
        -WorkingDirectory $RepoRoot

    Start-Sleep -Seconds 1

    Write-Step "spawning UI in a new terminal"
    Start-Process -FilePath $shellPath `
        -ArgumentList (@("-NoExit", "-File", $scriptPath, "-Frontend") + $passthru) `
        -WorkingDirectory $RepoRoot

    Write-Host ""
    Write-Ok "two terminals launched"
    Write-Host "  Backend : http://${Host_}:${Port}   (docs: http://${Host_}:${Port}/docs)"
    Write-Host "  UI      : http://localhost:5173"
    Write-Host "  Login   : tenant=browser_tenant  email=admin.browser@example.com"
    Write-Host "  Stop    : Ctrl+C in each window"
}

function Start-Both {
    $backendUrl = "http://${Host_}:${Port}"
    $env:TASKFORCE_API_URL = $backendUrl   # picked up by ui/vite.config.ts
    $needForce = Sync-ViteCacheForEnterpriseUi

    $jobs = @()

    Write-Step "starting backend on $backendUrl  (taskforce serve --reload)"
    $jobs += Start-Job -Name "backend" -ScriptBlock {
        param($repo, $h, $p)
        Set-Location $repo
        & .\.venv\Scripts\Activate.ps1
        taskforce serve --host $h --port $p --reload 2>&1
    } -ArgumentList $RepoRoot, $Host_, $Port

    Write-Step "starting UI on http://localhost:5173  (pnpm dev)"
    $jobs += Start-Job -Name "ui" -ScriptBlock {
        param($uiDir, $apiUrl, $force)
        Set-Location $uiDir
        $env:TASKFORCE_API_URL = $apiUrl
        if ($force) {
            & pnpm dev -- --force 2>&1
        } else {
            & pnpm dev 2>&1
        }
    } -ArgumentList $UiDir, $backendUrl, $needForce

    Write-Host ""
    Write-Host "----------------------------------------------------------------"
    Write-Host "  Backend : $backendUrl   (docs: $backendUrl/docs)"
    Write-Host "  UI      : http://localhost:5173"
    Write-Host "  Login   : tenant=browser_tenant  email=admin.browser@example.com"
    Write-Host "  Stop    : Ctrl+C"
    Write-Host "----------------------------------------------------------------"
    Write-Host ""

    try {
        while ($true) {
            foreach ($job in $jobs) {
                $output = Receive-Job -Job $job -Keep:$false
                if ($output) {
                    $prefix = if ($job.Name -eq "backend") { "[be]" } else { "[ui]" }
                    $color  = if ($job.Name -eq "backend") { "Magenta" } else { "Blue" }
                    foreach ($line in $output) {
                        Write-Host "$prefix $line" -ForegroundColor $color
                    }
                }
                if ($job.State -in @("Failed","Completed","Stopped")) {
                    Write-Warn2 "$($job.Name) job ended with state $($job.State)"
                    return
                }
            }
            Start-Sleep -Milliseconds 250
        }
    } finally {
        Write-Host ""
        Write-Step "shutting down"
        foreach ($job in $jobs) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
        # Kill any orphan child processes (uvicorn worker, vite, esbuild)
        Get-Process -Name "node","python","uvicorn" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "$RepoRoot*" -or $_.Path -like "$UiDir*" } |
            Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Ok "stopped"
    }
}

# ---------------------------------------------------------------- main
Test-Venv

if ($Build) {
    if (-not (Test-UiDeps) -or $Install) { Install-UiDeps }
    Invoke-Build
    exit 0
}

if ($Backend -and $Frontend) {
    Write-Err "use either -Backend or -Frontend (or neither for both, or -Split for both in separate terminals)"
    exit 1
}

if ($Split -and ($Backend -or $Frontend)) {
    Write-Err "-Split implies both backend and frontend; do not combine with -Backend / -Frontend"
    exit 1
}

# Determine which prereqs to satisfy. -Split needs both; otherwise mirror the
# single-mode flags. Default (no flags) = both.
$wantBackend  = $Split -or (-not $Frontend)
$wantFrontend = $Split -or (-not $Backend)

if ($wantBackend) {
    if ($Install -or -not (Test-EnterprisePlugin)) {
        Install-EnterprisePlugin
        if (-not (Test-EnterprisePlugin)) {
            Write-Err "enterprise plugin still not discoverable after install"
            exit 1
        }
    } else {
        Write-Ok "enterprise plugin: present"
    }
    if (-not $SkipMigrate) {
        Invoke-EnterpriseBootstrap
    }
}

if ($wantFrontend) {
    if ($Install -or -not (Test-UiDeps)) {
        Install-UiDeps
    } else {
        Write-Ok "UI deps: present"
    }
}

if ($Split) {
    Start-Split
    exit 0
}

if ($Backend) {
    Start-BackendForeground
    exit $LASTEXITCODE
}

if ($Frontend) {
    Start-FrontendForeground
    exit $LASTEXITCODE
}

Start-Both
