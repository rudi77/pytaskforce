-- =============================================================================
-- AP-Ledger Schema für österreichische Einnahmen-Überschuss-Rechnung (EÜR)
-- Zielgruppe: Selbständige Friseurin in Österreich
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- Kategorien (Einnahmen/Ausgaben)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    type            TEXT    NOT NULL CHECK (type IN ('expense', 'revenue')),
    description     TEXT,
    tax_deductible  INTEGER NOT NULL DEFAULT 1,
    default_tax_code TEXT   REFERENCES tax_codes(code),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------------
-- Steuersätze (Österreich)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tax_codes (
    code        TEXT    PRIMARY KEY,
    rate        REAL    NOT NULL,
    label       TEXT    NOT NULL,
    description TEXT,
    valid_from  TEXT    NOT NULL DEFAULT '2024-01-01',
    valid_to    TEXT
);

-- -----------------------------------------------------------------------------
-- Geschäftsperioden (Monate)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fiscal_periods (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    label       TEXT    NOT NULL,
    start_date  TEXT    NOT NULL,
    end_date    TEXT    NOT NULL,
    is_closed   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(year, month)
);

-- -----------------------------------------------------------------------------
-- Lieferanten / Geschäftspartner
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    name_normalized TEXT    NOT NULL,
    uid_number      TEXT,
    address         TEXT,
    default_category_code TEXT REFERENCES categories(code),
    default_tax_code      TEXT REFERENCES tax_codes(code),
    notes           TEXT,
    match_keywords  TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_vendors_normalized ON vendors(name_normalized);

-- -----------------------------------------------------------------------------
-- Belege (Rechnungen, Kassenbons, Gutschriften)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_ref    TEXT,
    vendor_id       INTEGER REFERENCES vendors(id),
    vendor_name_raw TEXT    NOT NULL,
    invoice_date    TEXT    NOT NULL,
    due_date        TEXT,
    total_gross     REAL    NOT NULL,
    total_net       REAL,
    total_tax       REAL,
    currency        TEXT    NOT NULL DEFAULT 'EUR',
    type            TEXT    NOT NULL DEFAULT 'invoice'
                           CHECK (type IN ('invoice', 'receipt', 'credit_note')),
    status          TEXT    NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'validated', 'posted', 'rejected')),
    source_file     TEXT,
    source_type     TEXT    CHECK (source_type IN ('photo', 'pdf', 'manual')),
    extraction_confidence REAL,
    fiscal_period_id INTEGER REFERENCES fiscal_periods(id),
    notes           TEXT,
    telegram_chat_id TEXT,
    telegram_message_id TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_vendor ON invoices(vendor_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);

-- -----------------------------------------------------------------------------
-- Belegpositionen
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoice_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL DEFAULT 1,
    description     TEXT    NOT NULL,
    quantity        REAL    NOT NULL DEFAULT 1,
    unit_price      REAL,
    net_amount      REAL    NOT NULL,
    tax_code        TEXT    REFERENCES tax_codes(code),
    tax_amount      REAL,
    gross_amount    REAL    NOT NULL,
    category_code   TEXT    REFERENCES categories(code),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice ON invoice_lines(invoice_id);

-- -----------------------------------------------------------------------------
-- Buchungssätze (Journal Entries)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS journal_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      INTEGER REFERENCES invoices(id),
    entry_date      TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'posted', 'reversed')),
    fiscal_period_id INTEGER REFERENCES fiscal_periods(id),
    posted_at       TEXT,
    posted_by       TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_date ON journal_entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_journal_entries_invoice ON journal_entries(invoice_id);

-- -----------------------------------------------------------------------------
-- Buchungszeilen (Soll/Haben)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS journal_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL DEFAULT 1,
    account_code    TEXT    NOT NULL,
    account_name    TEXT    NOT NULL,
    debit_amount    REAL    NOT NULL DEFAULT 0,
    credit_amount   REAL    NOT NULL DEFAULT 0,
    tax_code        TEXT    REFERENCES tax_codes(code),
    description     TEXT,
    CHECK (
        (debit_amount > 0 AND credit_amount = 0) OR
        (credit_amount > 0 AND debit_amount = 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_journal_lines_entry ON journal_lines(journal_entry_id);

-- -----------------------------------------------------------------------------
-- Audit Log (unveränderlich)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    entity_type TEXT    NOT NULL,
    entity_id   INTEGER NOT NULL,
    actor       TEXT    NOT NULL DEFAULT 'system',
    details     TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_type ON audit_log(event_type);

-- -----------------------------------------------------------------------------
-- EÜR-Zusammenfassung (View)
-- -----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_euer_summary AS
SELECT
    fp.year,
    fp.month,
    fp.label AS period,
    c.type AS category_type,
    c.name AS category_name,
    c.code AS category_code,
    SUM(il.gross_amount) AS total_gross,
    SUM(il.net_amount) AS total_net,
    SUM(il.tax_amount) AS total_tax,
    COUNT(DISTINCT i.id) AS invoice_count
FROM invoices i
JOIN invoice_lines il ON il.invoice_id = i.id
JOIN categories c ON c.code = il.category_code
LEFT JOIN fiscal_periods fp ON fp.id = i.fiscal_period_id
WHERE i.status = 'posted'
GROUP BY fp.year, fp.month, c.code
ORDER BY fp.year, fp.month, c.type, c.sort_order;

-- -----------------------------------------------------------------------------
-- Monatliche Zusammenfassung (View)
-- -----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_monthly_totals AS
SELECT
    fp.year,
    fp.month,
    fp.label AS period,
    SUM(CASE WHEN c.type = 'revenue' THEN il.net_amount ELSE 0 END) AS total_revenue,
    SUM(CASE WHEN c.type = 'expense' THEN il.net_amount ELSE 0 END) AS total_expenses,
    SUM(CASE WHEN c.type = 'revenue' THEN il.net_amount ELSE 0 END) -
    SUM(CASE WHEN c.type = 'expense' THEN il.net_amount ELSE 0 END) AS profit,
    SUM(CASE WHEN c.type = 'revenue' THEN il.tax_amount ELSE 0 END) AS tax_collected,
    SUM(CASE WHEN c.type = 'expense' THEN il.tax_amount ELSE 0 END) AS tax_paid,
    SUM(CASE WHEN c.type = 'revenue' THEN il.tax_amount ELSE 0 END) -
    SUM(CASE WHEN c.type = 'expense' THEN il.tax_amount ELSE 0 END) AS tax_liability
FROM invoices i
JOIN invoice_lines il ON il.invoice_id = i.id
JOIN categories c ON c.code = il.category_code
LEFT JOIN fiscal_periods fp ON fp.id = i.fiscal_period_id
WHERE i.status = 'posted'
GROUP BY fp.year, fp.month
ORDER BY fp.year, fp.month;
