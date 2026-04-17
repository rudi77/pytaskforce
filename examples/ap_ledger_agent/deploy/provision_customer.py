"""Provision a new BluBot customer instance.

Creates a per-customer directory under ``$BLUBOT_ROOT/customers/<slug>``
(default: ``C:\\blubot`` on Windows, ``/srv/blubot`` on POSIX), renders
the agent profile + .env from templates, and prints the next-step
instructions.

Usage:
  python provision_customer.py --slug anna-schmidt \\
                                --name "Anna Schmidt" \\
                                --country AT \\
                                [--blubot-root C:\\blubot] \\
                                [--repo-path C:\\Users\\rudi\\source\\pytaskforce]

The script is interactive for secrets:
  - Telegram bot token (from BotFather)
  - Telegram chat_id (the customer's chat with the bot — captured after
    the customer presses /start; or supply via --chat-id for testing)
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows so the script doesn't crash when printing
# non-ASCII characters (file paths with umlauts, friendly status icons).
if sys.platform == "win32" and isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_BLUBOT_ROOT_WINDOWS = r"C:\blubot"
DEFAULT_BLUBOT_ROOT_POSIX = "/srv/blubot"


def _default_blubot_root() -> Path:
    env = os.environ.get("BLUBOT_ROOT")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(DEFAULT_BLUBOT_ROOT_WINDOWS)
    return Path(DEFAULT_BLUBOT_ROOT_POSIX)


def _default_repo_path() -> Path:
    """The repo path is four levels up from this file:
    file → deploy → ap_ledger_agent → examples → repo-root."""
    return Path(__file__).resolve().parents[3]


def _scripts_dir(repo_path: Path) -> Path:
    return (
        repo_path
        / "examples"
        / "ap_ledger_agent"
        / "deploy"
        / "skills"
        / "ap-ledger"
        / "scripts"
    )


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def _render(template_path: Path, substitutions: dict[str, str]) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in substitutions.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _prompt(label: str, default: str | None = None) -> str:
    """Prompt for a value, defaulting to the given value if the user hits Enter.

    Refuses to prompt when stdin is not a TTY (e.g. piped or running in a
    restricted PowerShell context) — in that case the caller must supply
    the value via the corresponding CLI flag.
    """
    if not sys.stdin.isatty():
        raise SystemExit(
            f"[provision] Cannot prompt for '{label}': stdin is not a TTY.\n"
            f"  Pass the value via the matching CLI flag instead "
            f"(--bot-token / --chat-id)."
        )
    suffix = f" [{default}]" if default else ""
    try:
        while True:
            value = input(f"{label}{suffix}: ").strip()
            if value:
                return value
            if default is not None:
                return default
            print("  -> required, please enter a value.")
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("\n[provision] Aborted by user.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision a BluBot customer instance")
    parser.add_argument("--slug", required=True, help="URL/path-safe customer ID (e.g. anna-schmidt)")
    parser.add_argument("--name", required=True, help='Display name (e.g. "Anna Schmidt")')
    parser.add_argument("--country", default="AT", choices=["AT", "DE"], help="Tax country")
    parser.add_argument(
        "--blubot-root",
        type=Path,
        default=_default_blubot_root(),
        help="Root directory for all customers (default: C:\\blubot or /srv/blubot)",
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=_default_repo_path(),
        help="Path to the pytaskforce repo (used to locate deploy scripts)",
    )
    parser.add_argument("--bot-token", help="Telegram bot token (skip interactive prompt)")
    parser.add_argument("--chat-id", help="Telegram chat_id (skip interactive prompt)")
    parser.add_argument("--force", action="store_true", help="Overwrite if customer dir exists")
    args = parser.parse_args()

    customer_dir: Path = args.blubot_root / "customers" / args.slug
    scripts_dir = _scripts_dir(args.repo_path)

    # ── Sanity checks ────────────────────────────────────────────────
    if not scripts_dir.is_dir():
        print(f"❌ Scripts directory not found: {scripts_dir}")
        print(f"   Check --repo-path is the pytaskforce checkout root.")
        return 1

    if customer_dir.exists() and not args.force:
        print(f"❌ Customer directory already exists: {customer_dir}")
        print(f"   Use --force to overwrite, or delete it first.")
        return 1

    templates = _templates_dir()
    profile_tmpl = templates / "ap_ledger_agent.yaml.tmpl"
    llm_tmpl = templates / "llm_config.yaml"
    env_tmpl = templates / ".env.tmpl"
    for path in (profile_tmpl, llm_tmpl, env_tmpl):
        if not path.is_file():
            print(f"❌ Template missing: {path}")
            return 1

    # ── Interactive prompts for secrets ──────────────────────────────
    print(f"\nProvisioning customer: {args.name} (slug: {args.slug}, country: {args.country})")
    print(f"  Customer directory: {customer_dir}")
    print(f"  Scripts directory:  {scripts_dir}")
    print()

    bot_token = args.bot_token or _prompt("Telegram bot token (from @BotFather)")
    chat_id = args.chat_id or _prompt(
        "Telegram chat_id (customer presses /start, look for sender_id in log)"
    )

    # ── Create directory structure ───────────────────────────────────
    if customer_dir.exists() and args.force:
        print(f"\n⚠️  Removing existing {customer_dir}")
        shutil.rmtree(customer_dir)

    for sub in ("db", "belege", "reports", "exports", ".taskforce_ap_ledger"):
        (customer_dir / sub).mkdir(parents=True, exist_ok=True)

    # ── Render templates ─────────────────────────────────────────────
    substitutions = {
        "CUSTOMER_NAME": args.name,
        "COUNTRY": args.country,
        "CUSTOMER_DIR": str(customer_dir).replace("\\", "/"),
        "SCRIPTS_DIR": str(scripts_dir).replace("\\", "/"),
        "TELEGRAM_BOT_TOKEN": bot_token,
        "TELEGRAM_CHAT_ID": chat_id,
    }

    (customer_dir / "ap_ledger_agent.yaml").write_text(
        _render(profile_tmpl, substitutions), encoding="utf-8"
    )
    (customer_dir / "llm_config.yaml").write_text(
        llm_tmpl.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (customer_dir / ".env").write_text(
        _render(env_tmpl, substitutions), encoding="utf-8"
    )

    # ── Recap + next steps ───────────────────────────────────────────
    print(f"\n✓ Customer provisioned at: {customer_dir}")
    print(f"\nFiles created:")
    print(f"  ├── ap_ledger_agent.yaml   (agent profile)")
    print(f"  ├── llm_config.yaml        (model aliases)")
    print(f"  ├── .env                   (TELEGRAM_BOT_TOKEN, AP_LEDGER_*, ...)")
    print(f"  ├── db/                    (will hold ap-ledger.db on first booking)")
    print(f"  ├── belege/                (archived receipt files)")
    print(f"  ├── reports/               (generated PDFs)")
    print(f"  ├── exports/               (Belege ZIPs)")
    print(f"  └── .taskforce_ap_ledger/  (conversation history)")
    print()
    print("Next steps:")
    print(f"  1. Edit {customer_dir / '.env'} and add your AZURE_API_KEY etc.")
    if sys.platform == "win32":
        start_script = Path(__file__).resolve().parent / "start_customer.ps1"
        print(f"  2. Start the bot:")
        print(f"     pwsh {start_script} -Slug {args.slug}")
    else:
        start_script = Path(__file__).resolve().parent / "start_customer.sh"
        print(f"  2. Start the bot:")
        print(f"     {start_script} {args.slug}")
    print(f"  3. In Telegram, the customer presses /start on their bot.")
    print(f"     Send a Beleg or 'Schick mir den Jahresreport 2026' to test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
