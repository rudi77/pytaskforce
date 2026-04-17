<#
.SYNOPSIS
    Start a provisioned BluBot customer instance.

.DESCRIPTION
    Loads the customer's .env file, switches to the customer directory,
    and launches taskforce chat with telegram polling against the
    customer's profile YAML. Stays in the foreground — close the
    terminal or press Ctrl+Break to stop.

.PARAMETER Slug
    Customer slug (matches the directory under $env:BLUBOT_ROOT\customers\).

.PARAMETER BlubotRoot
    Override the default customer-root directory (default: $env:BLUBOT_ROOT
    or C:\blubot).

.PARAMETER RepoPath
    Override the path to the pytaskforce checkout (used for venv lookup).

.EXAMPLE
    pwsh start_customer.ps1 -Slug anna-schmidt
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Slug,

    [string]$BlubotRoot = $(if ($env:BLUBOT_ROOT) { $env:BLUBOT_ROOT } else { 'C:\blubot' }),

    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
)

$ErrorActionPreference = 'Stop'

$customerDir = Join-Path $BlubotRoot "customers\$Slug"
$envFile = Join-Path $customerDir '.env'
$profileFile = Join-Path $customerDir 'ap_ledger_agent.yaml'
$venvActivate = Join-Path $RepoPath '.venv\Scripts\Activate.ps1'

if (-not (Test-Path $customerDir)) {
    Write-Error "Customer directory not found: $customerDir`n  Provision it first: python $PSScriptRoot\provision_customer.py --slug $Slug --name '...'"
    exit 1
}
if (-not (Test-Path $envFile)) {
    Write-Error ".env file not found: $envFile"
    exit 1
}
if (-not (Test-Path $profileFile)) {
    Write-Error "Profile YAML not found: $profileFile"
    exit 1
}

# Load .env (KEY=VALUE per line, # comments ignored, blank lines ignored)
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) { return }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) { return }
    $key = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    # Strip surrounding quotes if present
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    Set-Item -Path "Env:$key" -Value $value
}

# Activate the repo's venv if available
if (Test-Path $venvActivate) {
    . $venvActivate
}
else {
    Write-Warning "venv activate script not found at $venvActivate — make sure 'taskforce' is on PATH."
}

Write-Host "▶ Starting BluBot for $Slug" -ForegroundColor Green
Write-Host "  Customer dir: $customerDir"
Write-Host "  Profile:      $profileFile"
Write-Host "  Press Ctrl+C for graceful shutdown, Ctrl+Break for force exit." -ForegroundColor Yellow
Write-Host ""

Push-Location $customerDir
try {
    & taskforce chat --telegram-polling --profile $profileFile
}
finally {
    Pop-Location
}
