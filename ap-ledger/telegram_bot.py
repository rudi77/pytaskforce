"""
AP-Ledger Telegram Bot
======================

Telegram-Frontend für die Beleg-Verarbeitung.
Empfängt Fotos/PDFs, startet den Claude-Workflow, sendet Ergebnisse zurück.

Setup:
    1. Bot erstellen via @BotFather in Telegram
    2. TELEGRAM_BOT_TOKEN in .env setzen
    3. python telegram_bot.py
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from claude_runner import ClaudeRunner

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PROJECT_DIR = Path(__file__).parent.resolve()
INVOICES_DIR = PROJECT_DIR / "invoices"
DB_PATH = PROJECT_DIR / "db" / "ap-ledger.db"

# Pending confirmations: chat_id -> workflow state
pending_confirmations: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Claude Runner Instanz
# ---------------------------------------------------------------------------
runner = ClaudeRunner(project_dir=str(PROJECT_DIR))


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Begrüßung und Anleitung."""
    await update.message.reply_text(
        "Hallo! Ich bin dein Buchhaltungs-Assistent.\n\n"
        "Schick mir einfach ein Foto oder PDF von einem Beleg "
        "(Rechnung, Kassenbon) und ich verbuche ihn für dich.\n\n"
        "Befehle:\n"
        "/status - Offene Belege anzeigen\n"
        "/monat - Monatsübersicht\n"
        "/export - CSV-Export für den Steuerberater\n"
        "/help - Hilfe anzeigen"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hilfe-Text."""
    await update.message.reply_text(
        "So funktioniert's:\n\n"
        "1. Mach ein Foto vom Beleg oder schick ein PDF\n"
        "2. Ich extrahiere die Daten automatisch\n"
        "3. Du bekommst eine Zusammenfassung zur Bestätigung\n"
        "4. Ein Tap auf ✅ und der Beleg ist verbucht!\n\n"
        "Wenn ich mir unsicher bin, frage ich nach.\n\n"
        "Befehle:\n"
        "/status - Offene Belege\n"
        "/monat - Monatsübersicht\n"
        "/export - CSV für Steuerberater\n"
        "/kategorien - Alle Kategorien anzeigen"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zeigt offene Belege."""
    result = await runner.run_query(
        f'sqlite3 -json "{DB_PATH}" '
        '"SELECT id, vendor_name_raw, invoice_date, total_gross, status '
        "FROM invoices WHERE status IN ('draft', 'validated') "
        'ORDER BY invoice_date DESC LIMIT 10;"'
    )
    try:
        rows = json.loads(result) if result.strip() else []
    except json.JSONDecodeError:
        rows = []

    if not rows:
        await update.message.reply_text("Keine offenen Belege. Alles erledigt! ✨")
        return

    lines = ["📋 Offene Belege:\n"]
    for row in rows:
        lines.append(
            f"• {row['invoice_date']} | {row['vendor_name_raw']} | "
            f"{row['total_gross']:.2f} € | {row['status']}"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_monat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Monatsübersicht."""
    result = await runner.run_query(
        f'sqlite3 -json "{DB_PATH}" "SELECT * FROM v_monthly_totals ORDER BY year DESC, month DESC LIMIT 3;"'
    )
    try:
        rows = json.loads(result) if result.strip() else []
    except json.JSONDecodeError:
        rows = []

    if not rows:
        await update.message.reply_text("Noch keine gebuchten Belege vorhanden.")
        return

    lines = ["📊 Monatsübersicht:\n"]
    for row in rows:
        lines.append(
            f"📅 {row['period']}:\n"
            f"   Einnahmen: {row.get('total_revenue', 0):.2f} €\n"
            f"   Ausgaben:  {row.get('total_expenses', 0):.2f} €\n"
            f"   Gewinn:    {row.get('profit', 0):.2f} €\n"
            f"   USt-Last:  {row.get('tax_liability', 0):.2f} €\n"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """CSV-Export generieren und senden."""
    import subprocess

    csv_path = PROJECT_DIR / "export_latest.csv"
    result = subprocess.run(
        [
            "sqlite3",
            "-header",
            "-csv",
            str(DB_PATH),
            "SELECT i.invoice_date as datum, v.name as lieferant, "
            "c.name as kategorie, il.net_amount as netto, "
            "il.tax_amount as ust, il.gross_amount as brutto, "
            "tc.label as steuersatz "
            "FROM invoices i "
            "JOIN invoice_lines il ON il.invoice_id = i.id "
            "LEFT JOIN vendors v ON v.id = i.vendor_id "
            "LEFT JOIN categories c ON c.code = il.category_code "
            "LEFT JOIN tax_codes tc ON tc.code = il.tax_code "
            "WHERE i.status = 'posted' "
            "ORDER BY i.invoice_date;",
        ],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        await update.message.reply_text("Keine gebuchten Belege für den Export.")
        return

    csv_path.write_text(result.stdout, encoding="utf-8")
    await update.message.reply_document(
        document=csv_path,
        filename="beleg_export.csv",
        caption="📎 Beleg-Export für den Steuerberater",
    )


async def cmd_kategorien(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zeigt alle Kategorien."""
    result = await runner.run_query(
        f'sqlite3 -json "{DB_PATH}" '
        '"SELECT code, name, type FROM categories ORDER BY sort_order;"'
    )
    try:
        rows = json.loads(result) if result.strip() else []
    except json.JSONDecodeError:
        rows = []

    expenses = [r for r in rows if r["type"] == "expense"]
    revenues = [r for r in rows if r["type"] == "revenue"]

    lines = ["📁 Kategorien:\n", "💰 Einnahmen:"]
    for r in revenues:
        lines.append(f"  • {r['name']} ({r['code']})")
    lines.append("\n💸 Ausgaben:")
    for r in expenses:
        lines.append(f"  • {r['name']} ({r['code']})")

    await update.message.reply_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Photo / Document Handler
# ---------------------------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verarbeitet eingehende Fotos."""
    await update.message.reply_text("📸 Beleg empfangen, wird verarbeitet...")

    # Foto in höchster Auflösung herunterladen
    photo = update.message.photo[-1]  # Höchste Auflösung
    file = await context.bot.get_file(photo.file_id)

    # Speichere unter invoices/
    INVOICES_DIR.mkdir(exist_ok=True)
    filename = f"beleg_{photo.file_unique_id}.jpg"
    file_path = INVOICES_DIR / filename
    await file.download_to_drive(str(file_path))

    await _process_invoice(update, context, str(file_path), "photo")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verarbeitet eingehende PDFs."""
    doc = update.message.document
    if doc.mime_type not in ("application/pdf", "image/jpeg", "image/png"):
        await update.message.reply_text(
            "Bitte schick mir ein Foto (JPG/PNG) oder ein PDF."
        )
        return

    await update.message.reply_text("📄 Dokument empfangen, wird verarbeitet...")

    file = await context.bot.get_file(doc.file_id)
    INVOICES_DIR.mkdir(exist_ok=True)
    filename = f"beleg_{doc.file_unique_id}_{doc.file_name}"
    file_path = INVOICES_DIR / filename
    await file.download_to_drive(str(file_path))

    source_type = "pdf" if doc.mime_type == "application/pdf" else "photo"
    await _process_invoice(update, context, str(file_path), source_type)


async def _process_invoice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_path: str,
    source_type: str,
) -> None:
    """Startet den Claude-Workflow für einen Beleg."""
    chat_id = update.effective_chat.id

    try:
        # Claude CLI Workflow starten
        result = await runner.process_invoice(file_path, source_type)

        if result.get("needs_user_input"):
            # HITL: User muss Kategorie wählen oder bestätigen
            pending_confirmations[chat_id] = result
            keyboard = _build_confirmation_keyboard(result)
            await update.message.reply_text(
                _format_summary(result),
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        elif result.get("error"):
            await update.message.reply_text(f"❌ Fehler: {result['error']}")
        else:
            # Auto-Buchung (hohe Confidence)
            pending_confirmations[chat_id] = result
            keyboard = _build_confirmation_keyboard(result)
            await update.message.reply_text(
                _format_summary(result),
                reply_markup=keyboard,
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Fehler bei Beleg-Verarbeitung: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Fehler bei der Verarbeitung: {str(e)}\n"
            "Bitte versuche es erneut oder schick den Beleg als PDF."
        )


def _format_summary(result: dict) -> str:
    """Formatiert die Zusammenfassung für Telegram."""
    data = result.get("extraction", {})
    suggestion = result.get("suggestion", {})

    vendor = data.get("vendor_name", "Unbekannt")
    date = data.get("invoice_date", "—")
    gross = data.get("total_gross", 0)
    net = data.get("total_net", gross)
    tax = data.get("total_tax", 0)
    category = suggestion.get("category_name", "Nicht zugeordnet")
    confidence = result.get("confidence", 0)

    conf_emoji = "🟢" if confidence >= 0.9 else "🟡" if confidence >= 0.7 else "🔴"

    return (
        f"📋 <b>Beleg erkannt</b>\n\n"
        f"🏪 {vendor}\n"
        f"📅 {date}\n"
        f"💰 {gross:.2f} € brutto\n"
        f"   ({net:.2f} € netto + {tax:.2f} € USt)\n"
        f"📁 Kategorie: {category}\n"
        f"{conf_emoji} Sicherheit: {confidence:.0%}\n"
    )


def _build_confirmation_keyboard(result: dict) -> InlineKeyboardMarkup:
    """Erstellt die Bestätigungs-Buttons."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Passt", callback_data="confirm"),
                InlineKeyboardButton("✏️ Korrigieren", callback_data="correct"),
                InlineKeyboardButton("❌ Ablehnen", callback_data="reject"),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Callback Handler (Button-Klicks)
# ---------------------------------------------------------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verarbeitet Button-Klicks."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    state = pending_confirmations.get(chat_id)

    if not state:
        await query.edit_message_text("⚠️ Keine ausstehende Bestätigung gefunden.")
        return

    if query.data == "confirm":
        await query.edit_message_text("⏳ Wird gebucht...")
        try:
            result = await runner.confirm_and_post(state)
            del pending_confirmations[chat_id]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Beleg gebucht!\n\n"
                f"Invoice #{result.get('invoice_id', '?')}\n"
                f"Journal #{result.get('journal_id', '?')}",
            )
        except Exception as e:
            logger.error(f"Fehler beim Buchen: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Fehler beim Buchen: {str(e)}",
            )

    elif query.data == "correct":
        del pending_confirmations[chat_id]
        await query.edit_message_text(
            "✏️ OK, was soll ich ändern?\n\n"
            "Schreib mir z.B.:\n"
            '• "Kategorie: Wareneinsatz"\n'
            '• "Betrag: 45,90"\n'
            '• "Lieferant: Wella"\n\n'
            "Oder schick den Beleg einfach nochmal."
        )

    elif query.data == "reject":
        if state:
            await runner.reject_invoice(state)
            del pending_confirmations[chat_id]
        await query.edit_message_text("❌ Beleg abgelehnt und archiviert.")


# ---------------------------------------------------------------------------
# Text Handler (für Korrekturen / Fragen)
# ---------------------------------------------------------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verarbeitet Textnachrichten (Fragen, Korrekturen)."""
    text = update.message.text

    # Wenn eine Korrektur aussteht, an Claude weiterleiten
    chat_id = update.effective_chat.id
    if chat_id in pending_confirmations:
        await update.message.reply_text("⏳ Verarbeite Korrektur...")
        result = await runner.apply_correction(
            pending_confirmations[chat_id], text
        )
        if result.get("updated"):
            pending_confirmations[chat_id] = result
            keyboard = _build_confirmation_keyboard(result)
            await update.message.reply_text(
                _format_summary(result),
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        return

    # Allgemeine Frage an Claude weiterleiten
    await update.message.reply_text("⏳ Denke nach...")
    response = await runner.ask_question(text)
    await update.message.reply_text(response)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Bot starten."""
    if not BOT_TOKEN:
        print("FEHLER: TELEGRAM_BOT_TOKEN ist nicht gesetzt!")
        print("1. Erstelle einen Bot via @BotFather in Telegram")
        print("2. Setze die Umgebungsvariable:")
        print("   export TELEGRAM_BOT_TOKEN='dein-token-hier'")
        return

    # DB initialisieren falls nötig
    if not DB_PATH.exists():
        import subprocess

        logger.info("Initialisiere Datenbank...")
        subprocess.run(
            ["bash", str(PROJECT_DIR / "scripts" / "init-db.sh"), str(DB_PATH)],
            check=True,
        )

    app = Application.builder().token(BOT_TOKEN).build()

    # Handler registrieren
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("hilfe", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("monat", cmd_monat))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("kategorien", cmd_kategorien))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot gestartet. Warte auf Nachrichten...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
