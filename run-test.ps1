# PowerShell-Skript: run-test.ps1
# Führt alle Unit-Tests mit pytest aus und zeigt die Coverage-Statistik an.
# Verwendet 'uv run' für die Ausführung im isolierten Environment.
# Siehe user-story.md für Anforderungen.

# Prüfe, ob uv installiert ist
$uv = $(uv --version 2>$null)
if (-not $uv) {
    Write-Host "[FEHLER] 'uv' ist nicht installiert oder nicht im PATH. Bitte installiere uv mit 'pip install uv'." -ForegroundColor Red
    exit 1
}

# Prüfe, ob pytest installiert ist (im uv-Environment)
$pytest = $(uv run python -m pytest --version 2>$null)
if (-not $pytest) {
    Write-Host "[FEHLER] pytest ist nicht installiert oder nicht im uv-Environment verfügbar. Bitte installiere pytest mit 'uv pip install pytest pytest-cov'." -ForegroundColor Red
    exit 1
}

# Prüfe, ob pytest-cov installiert ist (im uv-Environment)
$pytestcov = $(uv run python -m pytest --help | Select-String '--cov=')
if (-not $pytestcov) {
    Write-Host "[FEHLER] pytest-cov ist nicht installiert oder nicht im uv-Environment verfügbar. Bitte installiere es mit 'uv pip install pytest-cov'." -ForegroundColor Red
    exit 1
}

# Führe Tests mit Coverage im uv-Environment aus
Write-Host "Starte Tests mit Coverage (uv run)..." -ForegroundColor Cyan
uv run python -m pytest --cov . --cov-report term-missing

# Statuscode weitergeben
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FEHLER] Mindestens ein Test ist fehlgeschlagen." -ForegroundColor Red
    exit $LASTEXITCODE
} else {
    Write-Host "Alle Tests erfolgreich!" -ForegroundColor Green
}
