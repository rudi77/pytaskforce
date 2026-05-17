# ACP Showcase runner (Windows / PowerShell).
#
# Starts the researcher + coder peers in the background, waits for their
# ACP ports to come up, then runs a mission through the orchestrator
# profile that delegates to both peers.
#
# Usage:
#   .\examples\acp_showcase\run_demo.ps1
#   .\examples\acp_showcase\run_demo.ps1 "Custom mission text"

[CmdletBinding()]
param(
    [string]$Mission = 'Research the three most-used Python HTTP client libraries in 2026 and write a minimal working example using the recommended one. Save the example to examples/acp_showcase/out/demo_client.py.'
)

$ErrorActionPreference = 'Stop'

# Force UTF-8 for Python's stdout/stderr in every child process we spawn.
# Without this, Rich's progress bars / boxes (U+2554 etc.) crash with
# UnicodeEncodeError under the default Windows cp1252 codepage. Setting
# PYTHONIOENCODING via .env is too late — Python binds sys.stdout before
# dotenv loads — so we set it here in the parent shell so every child
# inherits it.
$env:PYTHONIOENCODING = 'utf-8'
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Best-effort; consoles without a writable encoding (e.g. some CI
    # runners) silently keep their default.
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Resolve-Path (Join-Path $scriptDir '..\..')
$logDir    = Join-Path $scriptDir 'logs'
$outDir    = Join-Path $scriptDir 'out'

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Set-Location $repoRoot

# We track the actual child processes (PowerShell jobs only kill the
# runspace and leave `uv`/`python`/`uvicorn` orphaned, which keeps the
# ACP ports bound so the next demo run fails). Start-Process -PassThru
# returns a Process object whose Id we can pass to Stop-Process.
$peers = @()

function Stop-Peers {
    if ($peers.Count -eq 0) { return }
    Write-Host ''
    Write-Host '[demo] Stopping background peers...'
    foreach ($peer in $peers) {
        try {
            if (-not $peer.HasExited) {
                # Kill the entire process tree: `uv run` spawns Python
                # which spawns uvicorn; killing only the parent leaves
                # the listener alive on the ACP port.
                taskkill /PID $peer.Id /T /F 2>&1 | Out-Null
            }
        } catch {
            # Best-effort cleanup.
        }
    }
}

function Wait-ForPort {
    param([int]$Port, [int]$Attempts = 120)
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $iar = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(500)
            if ($ok -and $client.Connected) {
                $client.Close()
                return $true
            }
            $client.Close()
        } catch {
            # Connection refused — retry.
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# --- sanity checks -------------------------------------------------------

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "[demo] 'uv' not found on PATH. Install uv first."
    exit 1
}

try {
    uv run python -c "import acp_sdk" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'acp-sdk missing' }
} catch {
    Write-Error '[demo] acp-sdk not installed. Run: uv sync --extra acp'
    exit 1
}

# --- start peers in background ------------------------------------------

try {
    $researcherLog = Join-Path $logDir 'researcher.log'
    $coderLog      = Join-Path $logDir 'coder.log'

    Write-Host "[demo] Starting researcher peer on :8801 (logs: $researcherLog)"
    $peers += Start-Process -FilePath 'uv' `
        -ArgumentList @('run', 'taskforce', 'acp', 'start', '--profile', 'showcase_researcher') `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $researcherLog `
        -RedirectStandardError "$researcherLog.err" `
        -NoNewWindow `
        -PassThru

    Write-Host "[demo] Starting coder peer on :8802 (logs: $coderLog)"
    $peers += Start-Process -FilePath 'uv' `
        -ArgumentList @('run', 'taskforce', 'acp', 'start', '--profile', 'showcase_coder') `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $coderLog `
        -RedirectStandardError "$coderLog.err" `
        -NoNewWindow `
        -PassThru

    Write-Host '[demo] Waiting for peers to become reachable (up to ~120s for cold-start)...'
    if (-not (Wait-ForPort -Port 8801)) {
        throw "Timed out waiting for researcher (8801). See $researcherLog."
    }
    if (-not (Wait-ForPort -Port 8802)) {
        throw "Timed out waiting for coder (8802). See $coderLog."
    }
    Write-Host '[demo] Peers up.'

    # --- run the orchestrator mission ----------------------------------
    Write-Host ''
    Write-Host '[demo] Running mission through orchestrator (profile: showcase_orchestrator)'
    Write-Host "[demo] Mission: $Mission"
    Write-Host '=========================================================================='

    # Pass the mission via array splatting so embedded quotes survive
    # PowerShell's native-command argument parser.
    $missionArgs = @('run', 'taskforce', 'run', 'mission', '--profile', 'showcase_orchestrator', $Mission)
    & uv @missionArgs
    $missionExit = $LASTEXITCODE

    Write-Host '=========================================================================='
    Write-Host '[demo] Output artefacts (if the coder produced any):'
    Get-ChildItem $outDir -ErrorAction SilentlyContinue | Format-Table -AutoSize
    Write-Host ''
    Write-Host "[demo] Peer logs are kept in $logDir for inspection."

    exit $missionExit
}
finally {
    Stop-Peers
}
