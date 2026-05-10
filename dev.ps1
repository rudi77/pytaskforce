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
#   .\dev.ps1 -SyncPlugins     # rebuild/relink UI plugins before starting
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
    [switch]$SyncPlugins,
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
$SyncPluginsScript = Join-Path $RepoRoot "scripts\sync-plugins.ps1"
$ViteCacheDir = Join-Path $UiDir "node_modules\.vite"
$EnterpriseUiDist = Join-Path $UiDir "node_modules\@taskforce\enterprise-ui\dist"
$ViteFingerprintFile = Join-Path $UiDir ".dev-fingerprint"

function Write-Step  { param($msg) Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2 { param($msg) Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "    $msg" -ForegroundColor Red }

function Import-DotEnv {
    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) {
        return
    }

    foreach ($line in Get-Content $envFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        if ($trimmed.StartsWith("export ")) {
            $trimmed = $trimmed.Substring(7).Trim()
        }

        $key, $value = $trimmed.Split("=", 2)
        $key = $key.Trim()
        if (-not $key) {
            continue
        }

        $value = $value.Trim().Trim('"').Trim("'")
        Set-Item -Path "env:$key" -Value $value
    }
}

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
    # Runs `taskforce-enterprise admin bootstrap` from the enterprise repo root.
    # Idempotent: applies any pending alembic migrations and creates the
    # bootstrap tenant/admin if missing. Env vars (DATABASE_URL,
    # TASKFORCE_BOOTSTRAP_*) come from .env via Import-DotEnv at startup and
    # are inherited by the child process.
    Write-Step "applying alembic migrations + bootstrap (idempotent)"
    $bootstrapExe = Join-Path $Venv "Scripts\taskforce-enterprise.exe"
    if (-not (Test-Path $bootstrapExe)) {
        Write-Warn2 "taskforce-enterprise.exe missing - skipping migrations"
        return
    }
    Push-Location $EnterpriseRoot
    try {
        & $bootstrapExe admin bootstrap
    } finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Err "bootstrap failed (exit $LASTEXITCODE) - start anyway, but the DB schema may be out of sync"
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

function Invoke-SyncPlugins {
    if (-not (Test-Path $SyncPluginsScript)) {
        Write-Err "sync-plugins.ps1 not found at $SyncPluginsScript"
        exit 1
    }
    Write-Step "syncing UI plugins"
    & $SyncPluginsScript
    if ($LASTEXITCODE -ne 0) {
        Write-Err "sync-plugins.ps1 failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
    Write-Ok "UI plugins synced"
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
        Write-Warn2 "enterprise-ui dist not found at $EnterpriseUiDist - skipping Vite cache check"
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
        Write-Step "enterprise-ui dist changed since last run - clearing Vite dep cache"
    } elseif (-not (Test-Path $ViteCacheDir)) {
        Write-Step "no Vite dep cache yet - will optimize on start"
    } else {
        Write-Step "no fingerprint stored - clearing Vite dep cache"
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
        Write-Err "taskforce.exe not found at $VenvTaskforce - run 'uv sync' first"
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
    $env:TASKFORCE_API_URL = $backendUrl   # picked up by ui/vite.config.ts and inherited by both children
    $needForce = Sync-ViteCacheForEnterpriseUi

    # We launch backend + UI as direct child processes (System.Diagnostics.Process)
    # rather than as PowerShell jobs. PSJobs run in their own runspace and we lose
    # ownership of grandchildren (cmd -> pnpm -> node -> esbuild, uvicorn watcher
    # -> worker), so Ctrl+C used to leave orphans behind. With direct children we
    # know each PID and can kill the whole subtree on shutdown via taskkill /T /F.

    $procs = New-Object System.Collections.ArrayList
    $subs  = New-Object System.Collections.ArrayList

    # ---------- backend: .venv\Scripts\taskforce.exe serve ... ----------
    $bePsi = New-Object System.Diagnostics.ProcessStartInfo
    $bePsi.FileName  = $VenvTaskforce
    $bePsi.Arguments = "serve --host $Host_ --port $Port --reload"
    $bePsi.WorkingDirectory        = $RepoRoot
    $bePsi.UseShellExecute         = $false
    $bePsi.CreateNoWindow          = $true
    $bePsi.RedirectStandardOutput  = $true
    $bePsi.RedirectStandardError   = $true
    $be = New-Object System.Diagnostics.Process
    $be.StartInfo = $bePsi

    # ---------- UI: cmd /c pnpm dev [-- --force] -----------------------
    # cmd.exe wraps the .cmd shim; CreateProcess can't launch .cmd directly
    # when UseShellExecute=false.
    $uiArgs = "/c pnpm dev"
    if ($needForce) { $uiArgs += " -- --force" }
    $uiPsi = New-Object System.Diagnostics.ProcessStartInfo
    $uiPsi.FileName  = $env:COMSPEC
    $uiPsi.Arguments = $uiArgs
    $uiPsi.WorkingDirectory        = $UiDir
    $uiPsi.UseShellExecute         = $false
    $uiPsi.CreateNoWindow          = $true
    $uiPsi.RedirectStandardOutput  = $true
    $uiPsi.RedirectStandardError   = $true
    $ui = New-Object System.Diagnostics.Process
    $ui.StartInfo = $uiPsi

    $beAction = {
        if ($null -ne $EventArgs.Data) {
            Write-Host "[be] $($EventArgs.Data)" -ForegroundColor Magenta
        }
    }
    $uiAction = {
        if ($null -ne $EventArgs.Data) {
            Write-Host "[ui] $($EventArgs.Data)" -ForegroundColor Blue
        }
    }

    Write-Step "starting backend on $backendUrl  (taskforce serve --reload)"
    [void]$subs.Add((Register-ObjectEvent -InputObject $be -EventName OutputDataReceived -Action $beAction))
    [void]$subs.Add((Register-ObjectEvent -InputObject $be -EventName ErrorDataReceived  -Action $beAction))
    [void]$be.Start()
    $be.BeginOutputReadLine()
    $be.BeginErrorReadLine()
    [void]$procs.Add($be)

    Write-Step "starting UI on http://localhost:5173  (pnpm dev)"
    [void]$subs.Add((Register-ObjectEvent -InputObject $ui -EventName OutputDataReceived -Action $uiAction))
    [void]$subs.Add((Register-ObjectEvent -InputObject $ui -EventName ErrorDataReceived  -Action $uiAction))
    [void]$ui.Start()
    $ui.BeginOutputReadLine()
    $ui.BeginErrorReadLine()
    [void]$procs.Add($ui)

    Write-Host ""
    Write-Host "----------------------------------------------------------------"
    Write-Host "  Backend : $backendUrl   (docs: $backendUrl/docs)"
    Write-Host "  UI      : http://localhost:5173"
    Write-Host "  Login   : tenant=browser_tenant  email=admin.browser@example.com"
    Write-Host "  Stop    : Ctrl+C"
    Write-Host "----------------------------------------------------------------"
    Write-Host ""

    # Ctrl+C handling: bypass PowerShell's pipeline-stop entirely. .NET fires
    # CancelKeyPress on its own native signal thread, where no PowerShell
    # runspace is available -- so a ScriptBlock cast to ConsoleCancelEventHandler
    # crashes the host with "There is no Runspace available". We compile a real
    # C# handler via Add-Type once per session; it only touches a static
    # ManualResetEventSlim and never re-enters the PS engine.
    if (-not ('TaskforceDevLauncherCancel' -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Threading;
public static class TaskforceDevLauncherCancel {
    public static readonly ManualResetEventSlim Signal = new ManualResetEventSlim(false);
    public static readonly ConsoleCancelEventHandler Handler = new ConsoleCancelEventHandler(OnCancel);
    private static void OnCancel(object sender, ConsoleCancelEventArgs e) {
        e.Cancel = true;
        Signal.Set();
    }
    public static void Reset() { Signal.Reset(); }
}
"@
    }
    [TaskforceDevLauncherCancel]::Reset()
    [Console]::add_CancelKeyPress([TaskforceDevLauncherCancel]::Handler)

    try {
        while (-not [TaskforceDevLauncherCancel]::Signal.IsSet) {
            if ($be.HasExited) { Write-Warn2 "backend exited (code $($be.ExitCode))"; break }
            if ($ui.HasExited) { Write-Warn2 "ui exited (code $($ui.ExitCode))"; break }
            # Returns true if signaled, false on timeout. Either way we re-check the loop guard.
            [void][TaskforceDevLauncherCancel]::Signal.Wait(250)
        }
    } finally {
        try { [Console]::remove_CancelKeyPress([TaskforceDevLauncherCancel]::Handler) } catch {}
        Write-Host ""
        Write-Step "shutting down"
        foreach ($p in $procs) {
            try {
                if ($p -and -not $p.HasExited) {
                    # /T = kill subtree (vite -> esbuild, uvicorn watcher -> worker), /F = force.
                    & taskkill.exe /T /F /PID $p.Id 2>$null | Out-Null
                }
            } catch {}
        }
        foreach ($s in $subs) {
            try { Unregister-Event -SubscriptionId $s.Id -ErrorAction SilentlyContinue } catch {}
            try { Remove-Job          -Id $s.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
        Write-Ok "stopped"
    }
}

# ---------------------------------------------------------------- main
Test-Venv
Import-DotEnv

if ($SyncPlugins) {
    Invoke-SyncPlugins
}

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
