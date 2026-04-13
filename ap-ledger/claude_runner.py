"""
Claude CLI Runner
=================

Wrapper für Claude Code CLI als Subprocess.
Orchestriert den Beleg-Workflow über CLAUDE.md und Subagents.

Verwendung:
    runner = ClaudeRunner(project_dir="/pfad/zu/ap-ledger")
    result = await runner.process_invoice("/pfad/zum/beleg.jpg", "photo")
"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class ClaudeRunner:
    """Steuert Claude Code CLI als Subprocess für den AP-Workflow."""

    def __init__(self, project_dir: str | None = None):
        self.project_dir = Path(project_dir or Path(__file__).parent).resolve()
        self.db_path = self.project_dir / "db" / "ap-ledger.db"

    async def process_invoice(self, file_path: str, source_type: str) -> dict:
        """Verarbeitet einen Beleg durch den kompletten Workflow.

        Args:
            file_path: Pfad zur Beleg-Datei (Foto/PDF)
            source_type: 'photo' oder 'pdf'

        Returns:
            Dict mit Extraktionsergebnis, Vorschlag, Confidence
        """
        prompt = (
            f"Verarbeite diesen Beleg: {file_path}\n"
            f"Quellentyp: {source_type}\n\n"
            "Führe folgende Schritte aus:\n"
            "1. Extrahiere die Daten aus dem Beleg (verwende den Extractor Subagent)\n"
            "2. Suche den Vendor in der DB\n"
            "3. Ermittle die Geschäftsperiode\n"
            "4. Validiere die Daten\n"
            "5. Erstelle einen Kontierungsvorschlag\n\n"
            "Gib das Ergebnis als JSON zurück mit den Feldern:\n"
            '- "extraction": Die extrahierten Belegdaten\n'
            '- "vendor": Vendor-Match aus der DB (oder null)\n'
            '- "suggestion": Kontierungsvorschlag mit category_code, category_name\n'
            '- "confidence": Gesamt-Confidence (0.0-1.0)\n'
            '- "needs_user_input": true wenn User bestätigen muss\n'
            '- "validation": Validierungsergebnis\n\n'
            "Antworte NUR mit dem JSON, kein zusätzlicher Text."
        )

        output = await self._run_claude(prompt)
        return self._parse_workflow_result(output, file_path, source_type)

    async def confirm_and_post(self, state: dict) -> dict:
        """Bestätigt und bucht einen Beleg.

        Args:
            state: Workflow-State aus process_invoice()

        Returns:
            Dict mit invoice_id und journal_id
        """
        extraction = state.get("extraction", {})
        suggestion = state.get("suggestion", {})

        prompt = (
            "Der User hat den folgenden Beleg bestätigt. "
            "Führe jetzt die Buchung durch:\n\n"
            f"Extrahierte Daten: {json.dumps(extraction, ensure_ascii=False)}\n"
            f"Kontierungsvorschlag: {json.dumps(suggestion, ensure_ascii=False)}\n"
            f"Quelldatei: {state.get('source_file', '')}\n"
            f"Quellentyp: {state.get('source_type', 'photo')}\n\n"
            "Schritte:\n"
            "1. Speichere den Beleg (persist-invoice.sh)\n"
            "2. Erstelle den Journal-Eintrag (Ledger Builder + persist-journal.sh)\n"
            "3. Buche den Eintrag (post-journal.sh)\n"
            "4. Schreibe Audit-Log-Einträge\n\n"
            "Gib das Ergebnis als JSON zurück:\n"
            '{"invoice_id": ..., "journal_id": ..., "status": "posted"}'
        )

        output = await self._run_claude(prompt)
        return self._parse_json_safe(output, {"invoice_id": None, "journal_id": None})

    async def reject_invoice(self, state: dict) -> None:
        """Lehnt einen Beleg ab und schreibt Audit-Log."""
        extraction = state.get("extraction", {})
        vendor = extraction.get("vendor_name", "Unbekannt")

        # Direkt via Script, braucht kein Claude
        await self.run_query(
            f'bash {self.project_dir}/scripts/write-audit.sh '
            f'"{self.db_path}" "invoice_rejected" "invoice" 0 "user" '
            f"'{json.dumps({\"vendor\": vendor, \"reason\": \"user_rejected\"}, ensure_ascii=False)}'"
        )

    async def apply_correction(self, state: dict, correction_text: str) -> dict:
        """Wendet eine User-Korrektur auf den aktuellen State an."""
        prompt = (
            f"Der User möchte eine Korrektur am Beleg vornehmen.\n\n"
            f"Aktueller State: {json.dumps(state, ensure_ascii=False)}\n"
            f"Korrektur vom User: {correction_text}\n\n"
            "Wende die Korrektur an und gib den aktualisierten State zurück.\n"
            "Gleiche JSON-Struktur wie vorher, aber mit den Korrekturen.\n"
            'Setze "updated": true im Ergebnis.'
        )

        output = await self._run_claude(prompt)
        result = self._parse_json_safe(output, state)
        result["updated"] = True
        return result

    async def ask_question(self, question: str) -> str:
        """Stellt eine allgemeine Frage an Claude im Kontext des AP-Ledger.

        Args:
            question: Frage des Users

        Returns:
            Antwort als Text
        """
        prompt = (
            f"Der User hat eine Frage zur Buchhaltung:\n\n"
            f"{question}\n\n"
            "Beantworte die Frage kurz und verständlich. "
            "Wenn nötig, führe SQL-Abfragen gegen die Datenbank aus. "
            "Antworte auf Deutsch."
        )

        return await self._run_claude(prompt)

    async def run_query(self, query: str) -> str:
        """Führt einen Shell-Befehl direkt aus (für einfache DB-Abfragen)."""
        result = await asyncio.to_thread(
            subprocess.run,
            query,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(self.project_dir),
            timeout=30,
        )
        return result.stdout

    # -----------------------------------------------------------------------
    # Private Methods
    # -----------------------------------------------------------------------
    async def _run_claude(self, prompt: str, timeout: int = 120) -> str:
        """Führt Claude Code CLI als Subprocess aus.

        Args:
            prompt: Der Prompt für Claude
            timeout: Timeout in Sekunden

        Returns:
            Claude's Ausgabe als String
        """
        cmd = [
            "claude",
            "--print",         # Nur Output, kein interaktiver Modus
            "--dangerously-skip-permissions",  # Non-interactive
            "--prompt", prompt,
        ]

        logger.info("Starte Claude CLI...")
        logger.debug(f"Prompt: {prompt[:200]}...")

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=timeout,
                env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "ap-ledger"},
            )

            if result.returncode != 0:
                logger.error(f"Claude CLI Fehler: {result.stderr}")
                raise RuntimeError(f"Claude CLI fehlgeschlagen: {result.stderr[:500]}")

            output = result.stdout.strip()
            logger.info(f"Claude CLI Output: {len(output)} Zeichen")
            logger.debug(f"Output: {output[:500]}...")
            return output

        except subprocess.TimeoutExpired:
            logger.error(f"Claude CLI Timeout nach {timeout}s")
            raise TimeoutError(f"Claude CLI Timeout nach {timeout} Sekunden")

    def _parse_workflow_result(
        self, output: str, file_path: str, source_type: str
    ) -> dict:
        """Parst das Workflow-Ergebnis aus Claude's Output."""
        result = self._parse_json_safe(output, {})

        # Sicherstellen dass alle Felder vorhanden sind
        result.setdefault("extraction", {})
        result.setdefault("vendor", None)
        result.setdefault("suggestion", {})
        result.setdefault("confidence", 0.5)
        result.setdefault("needs_user_input", True)
        result.setdefault("validation", {"is_valid": True})
        result["source_file"] = file_path
        result["source_type"] = source_type

        return result

    def _parse_json_safe(self, text: str, default: dict) -> dict:
        """Versucht JSON aus dem Text zu extrahieren."""
        # Versuche direkt
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # Suche nach JSON-Block im Text
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Suche nach dem ersten { ... } Block
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning(f"Konnte kein JSON parsen aus: {text[:200]}...")
        return default


# ---------------------------------------------------------------------------
# Standalone Usage
# ---------------------------------------------------------------------------
async def main():
    """Standalone-Test: Beleg verarbeiten."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python claude_runner.py <datei.jpg|pdf>")
        print("       python claude_runner.py --query 'SQL-Query'")
        sys.exit(1)

    runner = ClaudeRunner()

    if sys.argv[1] == "--query":
        query = " ".join(sys.argv[2:])
        result = await runner.ask_question(query)
        print(result)
    else:
        file_path = sys.argv[1]
        source_type = "pdf" if file_path.lower().endswith(".pdf") else "photo"
        result = await runner.process_invoice(file_path, source_type)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
