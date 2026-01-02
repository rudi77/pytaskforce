"""Einfaches Skript zum Starten des Taskforce API Servers."""

import os
import sys
import uvicorn

# Pfad zum taskforce Modul hinzufügen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from taskforce.api.server import app

if __name__ == "__main__":
    # Konfiguration aus Umgebungsvariablen oder Standardwerte
    host = os.getenv("TASKFORCE_HOST", "0.0.0.0")
    port = int(os.getenv("TASKFORCE_PORT", "8030"))
    loglevel = os.getenv("LOGLEVEL", "info").lower()
    
    print(f"Starte Taskforce API Server auf http://{host}:{port}")
    print(f"API Dokumentation: http://localhost:{port}/docs")
    print("Drücken Sie Ctrl+C zum Beenden\n")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=loglevel,
    )

