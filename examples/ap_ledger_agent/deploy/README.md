# BluBot Deployment

How to onboard, run, back up, and remove a paying customer of the
AP-Ledger agent ("BluBot"). Built for the **MVP-A Concierge model**:
one bot per customer, manual onboarding by Rudi, no self-service yet.

---

## Layout

Each customer gets an isolated directory. The framework lives once,
shared across customers via the venv.

```
$BLUBOT_ROOT/                      (default: C:\blubot or /srv/blubot)
└── customers/
    ├── anna-schmidt/
    │   ├── ap_ledger_agent.yaml   (rendered from templates/ap_ledger_agent.yaml.tmpl)
    │   ├── llm_config.yaml
    │   ├── .env                   (TELEGRAM_BOT_TOKEN, AZURE_API_KEY, ...)
    │   ├── db/ap-ledger.db        (created on first booking)
    │   ├── belege/YYYY/MM/...     (archived receipt photos/PDFs)
    │   ├── reports/YYYY/...pdf    (generated PDF reports)
    │   ├── exports/...zip         (Belege-ZIPs for Steuerberater)
    │   └── .taskforce_ap_ledger/  (conversation history, agent state)
    └── max-mueller/  (same structure)
```

The agent itself runs as a foreground process per customer. For local
testing, just open one terminal per customer. Hetzner deployment with
systemd auto-restart is a Phase-2 step (see *Production Roadmap* below).

---

## Prerequisites (one-time)

1. **Python venv** in the repo: `uv sync` from the pytaskforce root.
2. **PowerShell 7+** on Windows (`pwsh`), or bash on Linux.
3. **A Telegram account** to chat with each customer's bot during
   testing — separate from the customer's account, so you can simulate
   their first `/start`.
4. **An Azure OpenAI deployment** of `gpt-5.4-mini` reachable via
   `AZURE_API_KEY` / `AZURE_API_BASE` / `AZURE_API_VERSION`.

---

## Onboarding a customer (Step-by-Step)

### 1. Create a Telegram bot

In Telegram, message **@BotFather**:

```
/newbot
→ Bot name: Anna's Beleg-Bot
→ Bot username: anna_belegbot   (must end in _bot, must be unique)
```

BotFather replies with a token like `1234567:ABC...XYZ`. **Copy it.**

Optional: `/setdescription`, `/setuserpic`, `/setcommands` to give the
bot a profile.

### 2. Provision the customer

```powershell
# Windows
python examples/ap_ledger_agent/deploy/provision_customer.py `
    --slug anna-schmidt `
    --name "Anna Schmidt" `
    --country AT
```

```bash
# Linux/macOS
python examples/ap_ledger_agent/deploy/provision_customer.py \
    --slug anna-schmidt \
    --name "Anna Schmidt" \
    --country AT
```

The script:
- Creates `$BLUBOT_ROOT/customers/anna-schmidt/` with subdirs.
- Asks for the **bot token** (paste from BotFather).
- Asks for the **chat_id** — for first onboarding you can put a
  placeholder `0`; we update it in step 4 after the customer talks.
  Or, if you already know it (e.g. you're testing with your own
  Telegram), enter it directly.
- Renders `ap_ledger_agent.yaml`, `llm_config.yaml`, `.env` from the
  templates with the customer's name/country/etc. substituted in.

### 3. Add LLM credentials

Open `$BLUBOT_ROOT/customers/anna-schmidt/.env` and uncomment / fill in
the Azure (or other provider) keys:

```ini
AZURE_API_KEY=...
AZURE_API_BASE=https://...
AZURE_API_VERSION=2024-12-01-preview
```

### 4. Capture the customer's chat_id

The customer presses `/start` on their bot. The agent's debug log shows:

```
telegram_poller.inbound_message has_attachments=False sender_id=5865840420 ...
```

That `sender_id` is the chat_id. **If you put a placeholder `0` in
step 2**, edit the customer's `ap_ledger_agent.yaml` and replace the
`default_recipient_id: "0"` with the real chat_id, then restart the bot.

(For inbound replies, the gateway auto-registers the chat_id
automatically — `default_recipient_id` is only needed for *proactive*
push notifications like sending a PDF report.)

### 5. Start the bot

```powershell
# Windows
pwsh examples/ap_ledger_agent/deploy/start_customer.ps1 -Slug anna-schmidt
```

```bash
# Linux/macOS
examples/ap_ledger_agent/deploy/start_customer.sh anna-schmidt
```

The bot stays in the foreground, polling Telegram. Customer can now
send Belege.

---

## Day-to-day operations

### Backup a customer

```bash
tar czf anna-schmidt-$(date +%F).tar.gz \
    -C "$BLUBOT_ROOT/customers" anna-schmidt
```

Encrypt and upload to off-site storage (Hetzner Storage Box, S3, etc.).
The whole customer state is in that one directory.

### Restore a customer

```bash
tar xzf anna-schmidt-2026-04-17.tar.gz -C "$BLUBOT_ROOT/customers"
```

Then run `start_customer` as usual.

### Update the framework

```bash
cd /path/to/pytaskforce
git pull
uv sync
```

Then restart each running customer (the bots will pick up the new code).

### Delete a customer

```bash
# 1. Stop the bot (Ctrl+C in the customer's terminal)
# 2. Optionally back up (see above)
# 3. Remove the customer directory
rm -rf "$BLUBOT_ROOT/customers/anna-schmidt"
# 4. (Optional) Delete the bot in BotFather: /mybots → choose → Delete Bot
```

---

## Customer-name flow into PDFs

The provisioning script writes `AP_LEDGER_CUSTOMER_NAME=Anna Schmidt`
into the customer's `.env`. The report scripts (`report_monthly_pdf.py`,
`report_annual_eur_pdf.py`, `export_belege_zip.py`) pick that up via
their `--customer` argument's default. The system prompt does **not**
need to know the name — it just calls the script and the name appears
on the PDF/ZIP automatically.

If you ever want to override per-call (e.g. to generate a report for
a different mandant), pass `--customer "Other Name"` explicitly.

---

## Production Roadmap (Phase 2)

For the first 3-5 pilot customers, the manual foreground-process model
above is fine. Once you have more customers / want auto-restart on
crash / want unattended boot, add:

1. **systemd unit per customer** on Hetzner (Linux):
   `blubot@.service` template that runs `start_customer.sh %i`.
   Enable per customer: `systemctl enable --now blubot@anna-schmidt`.
2. **Daily backup cron** to Hetzner Storage Box (encrypted).
3. **Centralised log shipping** (journalctl → Loki, or per-customer
   log files rotated by logrotate).
4. **Health-check script** that pings each bot's `getMe` endpoint and
   alerts you on Telegram if any are down.

These can land as `deploy/install_server.sh`, `deploy/blubot@.service`,
`deploy/backup.sh`, `deploy/healthcheck.py` once the pilot validates
the model.

---

## Files in this directory

| File | Purpose |
|---|---|
| `templates/ap_ledger_agent.yaml.tmpl` | Profile template with `{{CUSTOMER_NAME}}`, `{{COUNTRY}}`, `{{SCRIPTS_DIR}}`, `{{TELEGRAM_CHAT_ID}}`, `{{CUSTOMER_DIR}}` placeholders |
| `templates/llm_config.yaml` | Per-customer LLM aliases (copied verbatim) |
| `templates/.env.tmpl` | Env file template with all `AP_LEDGER_*` and `TELEGRAM_BOT_TOKEN` vars |
| `provision_customer.py` | One-shot scaffolder (cross-platform Python) |
| `start_customer.ps1` | Windows launcher (PowerShell) |
| `start_customer.sh` | POSIX launcher (bash) |
| `skills/ap-ledger/` | Self-contained skill bundle (scripts + sqlite_store, used by every customer instance) |
