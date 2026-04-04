"""Setup script for the Dateiverwaltung benchmark.

Copies 15 test documents from the user's Private folder into a temporary
benchmark directory and creates the expected category target folders.

Usage:
    from tests.benchmarks.autooptim.fixtures.setup_datei_benchmark import setup, cleanup

    work_dir = setup()   # Returns Path to temp benchmark dir
    # ... run benchmark ...
    cleanup(work_dir)     # Removes temp dir
"""

import shutil
import tempfile
from pathlib import Path

# Source documents (relative to C:\Users\rudi\Documents\Private)
PRIVATE_DIR = Path("C:/Users/rudi/Documents/Private")

TEST_DOCUMENTS = [
    "Arbeitsunfaehigkeitsbescheinigung_2024-02-07_105752.pdf",
    "Arzt/MRT-Befund-LinkesKnie_2025-12-04_115718.pdf",
    "Barmer/Steuerbescheid2021.pdf",
    "Bürgschaft Mietvertrag.pdf",
    "Emilia/Mietvertrag/mietvertrag_wien_1180.pdf",
    "Familienkasse/bescheid_kindergeld_2025-11-02_193555.pdf",
    "Kostenvoranschlag_Ausmalen_Haus_mit_Flaechen.pdf",
    "Lohnset_2023_09.pdf",
    "passport_2024-11-17_132359.pdf",
    "Einwilligungserklärung Dittrich Rudolf.pdf",
    "Barmer/einnahmeerklaerung.pdf",
    "Familienkasse/einspruch_familienkasse.docx",
    "Finanzamt/Ew_1-03__Man_.pdf",
    "feature_request_user_context.pdf",
    "24_anlage-08_nutzungsaufnahme_2021.pdf",
]

# Expected categories (agent should create/use these)
CATEGORIES = [
    "Gesundheit",
    "Finanzen",
    "Vertraege",
    "Behoerden",
    "Ausweise",
    "Formulare",
    "Sonstiges",
]


def setup() -> Path:
    """Create benchmark directory with test documents.

    Returns:
        Path to the temporary benchmark directory containing:
        - inbox/  (15 documents to categorize)
        - sorted/ (empty target directory for categorized documents)
    """
    work_dir = Path(tempfile.mkdtemp(prefix="datei_benchmark_"))

    inbox = work_dir / "inbox"
    inbox.mkdir()

    sorted_dir = work_dir / "sorted"
    sorted_dir.mkdir()

    # Copy test documents into inbox (flat, no subdirectories)
    copied = 0
    for doc_path in TEST_DOCUMENTS:
        src = PRIVATE_DIR / doc_path
        if src.exists():
            dst = inbox / src.name
            shutil.copy2(src, dst)
            copied += 1

    if copied == 0:
        raise FileNotFoundError(
            f"No test documents found in {PRIVATE_DIR}. "
            "Ensure the Private folder contains the expected files."
        )

    return work_dir


def cleanup(work_dir: Path) -> None:
    """Remove the temporary benchmark directory."""
    if work_dir.exists() and "datei_benchmark_" in work_dir.name:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    d = setup()
    print(f"Benchmark dir: {d}")
    print(f"Inbox files: {list((d / 'inbox').iterdir())}")
    print(f"Sorted dir: {d / 'sorted'}")
