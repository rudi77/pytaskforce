# sync-plugins.ps1
#
# Rebuild every UI workspace package after a plugin change so the host
# dev-server picks up the new bundle. Solves the "I changed the plugin
# but my browser still loads the old chunk" problem in three places at
# once:
#
#   1. ``pnpm build`` in @taskforce/ui-shell    — peerdep types
#   2. ``pnpm install --force`` + ``pnpm build`` in @taskforce/enterprise-ui
#   3. ``pnpm install --force`` in pytaskforce/ui plus a wipe of
#      ``node_modules/.vite`` so Vite's pre-bundled dep cache is rebuilt
#
# Usage:
#   .\scripts\sync-plugins.ps1
#
# Run this whenever you (or Claude) change source files inside
#   - packages/ui-shell/src
#   - ../taskforce-enterprise/web/src
# and your dev-server is running. Stop the dev-server first; the
# script does NOT restart it for you (it would lose your terminal).

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Resolve-Path (Join-Path $scriptDir '..')
$uiShell   = Join-Path $repoRoot 'packages\ui-shell'
$hostUi    = Join-Path $repoRoot 'ui'
$enterprise = Resolve-Path (Join-Path $repoRoot '..\taskforce-enterprise\web')

function Step([string]$label, [scriptblock]$body) {
    Write-Host ''
    Write-Host "[sync] $label" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[sync] step failed: $label (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}

Step 'Build @taskforce/ui-shell' {
    Set-Location $uiShell
    pnpm approve-builds --all
    pnpm build
}

Step 'Re-link + build @taskforce/enterprise-ui' {
    Set-Location $enterprise
    pnpm install --force
    pnpm approve-builds --all
    pnpm build
}

Step 'Re-link plugin into host UI' {
    Set-Location $hostUi
    pnpm install --force
    pnpm approve-builds --all
}

Step 'Wipe Vite pre-bundled dep cache' {
    $viteCache = Join-Path $hostUi 'node_modules\.vite'
    if (Test-Path $viteCache) {
        Remove-Item -Recurse -Force $viteCache
        Write-Host "  removed $viteCache"
    } else {
        Write-Host '  no .vite cache to clear'
    }
}

Set-Location $repoRoot
Write-Host ''
Write-Host '[sync] Done. If your dev-server was running, restart it now.' -ForegroundColor Green
Write-Host '[sync] Then in the browser: hard refresh (Ctrl+Shift+R) or open an incognito tab.' -ForegroundColor Green
