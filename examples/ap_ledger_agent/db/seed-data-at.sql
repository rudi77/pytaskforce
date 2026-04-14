-- =============================================================================
-- Seed-Daten: Österreichische Friseurin / Einzelunternehmen
-- =============================================================================

-- Steuersätze Österreich
INSERT OR IGNORE INTO tax_codes (code, rate, label, description) VALUES
    ('AT_20',   0.20, '20% USt',  'Normalsteuersatz Österreich'),
    ('AT_10',   0.10, '10% USt',  'Ermäßigter Steuersatz (Lebensmittel, Bücher)'),
    ('AT_13',   0.13, '13% USt',  'Ermäßigter Steuersatz (Blumen, Kunstgegenstände)'),
    ('AT_0',    0.00, '0% USt',   'Steuerbefreit (Versicherung, Miete Wohnung)'),
    ('EU_RC',   0.00, 'Reverse Charge', 'Innergemeinschaftlicher Erwerb / Reverse Charge');

-- Einnahmen-Kategorien
INSERT OR IGNORE INTO categories (code, name, type, description, default_tax_code, sort_order) VALUES
    ('einnahmen_bar',       'Bareinnahmen',           'revenue', 'Tageslosung / Kasseneinnahmen', 'AT_20', 10),
    ('einnahmen_karte',     'Karteneinnahmen',        'revenue', 'Bankomat / Kreditkarte',        'AT_20', 20),
    ('einnahmen_gutschein', 'Gutschein-Einlösung',    'revenue', 'Eingelöste Gutscheine',         'AT_20', 30),
    ('einnahmen_sonstige',  'Sonstige Einnahmen',     'revenue', 'Trinkgeld, Provisionen etc.',   'AT_20', 40);

-- Ausgaben-Kategorien (Friseur-spezifisch)
INSERT OR IGNORE INTO categories (code, name, type, description, default_tax_code, sort_order) VALUES
    ('waren_farbe',         'Haarfarben & Chemie',    'expense', 'Colorationen, Blondierung, Dauerwelle',    'AT_20', 100),
    ('waren_pflege',        'Pflegeprodukte',         'expense', 'Shampoo, Conditioner, Kur, Styling',       'AT_20', 110),
    ('waren_verbrauch',     'Verbrauchsmaterial',      'expense', 'Handschuhe, Alufolie, Umhänge, Handtücher','AT_20', 120),
    ('waren_verkauf',       'Verkaufsware',           'expense', 'Produkte zum Weiterverkauf an Kunden',     'AT_20', 130),
    ('miete',               'Miete Geschäftslokal',   'expense', 'Geschäftsraummiete',            'AT_20', 200),
    ('betriebskosten',      'Betriebskosten',         'expense', 'Strom, Wasser, Heizung, Müll',  'AT_20', 210),
    ('versicherung',        'Versicherungen',         'expense', 'Betriebshaftpflicht, Inventar', 'AT_0',  220),
    ('telefon_internet',    'Telefon & Internet',     'expense', 'Festnetz, Mobil, Internet',     'AT_20', 230),
    ('werbung',             'Werbung & Marketing',    'expense', 'Visitenkarten, Social Media',   'AT_20', 240),
    ('fortbildung',         'Fortbildung',            'expense', 'Seminare, Kurse, Messen',       'AT_20', 250),
    ('geraete',             'Geräte & Werkzeug',      'expense', 'Schere, Föhn, Glätteisen',      'AT_20', 260),
    ('einrichtung',         'Einrichtung & Ausstattung','expense','Möbel, Spiegel, Waschplatz',   'AT_20', 270),
    ('buero',               'Bürobedarf',             'expense', 'Papier, Druckerpatronen, Ordner','AT_20', 280),
    ('kfz',                 'KFZ-Kosten',             'expense', 'Betriebliche Fahrten, Tanken',  'AT_20', 290),
    ('bank',                'Bankgebühren',           'expense', 'Kontoführung, Kartengebühren',  'AT_0',  300),
    ('steuerberater',       'Steuerberatung',         'expense', 'Steuerberater, Buchhaltung',    'AT_20', 310),
    ('reinigung',           'Reinigung',              'expense', 'Reinigungsmittel, Putzdienst',  'AT_20', 320),
    ('sonstige_ausgaben',   'Sonstige Ausgaben',      'expense', 'Nicht zuordenbare Ausgaben',    'AT_20', 900);

-- Geschäftsperioden 2025 & 2026
INSERT OR IGNORE INTO fiscal_periods (year, month, label, start_date, end_date) VALUES
    (2025,  1, 'Jänner 2025',    '2025-01-01', '2025-01-31'),
    (2025,  2, 'Februar 2025',   '2025-02-01', '2025-02-28'),
    (2025,  3, 'März 2025',      '2025-03-01', '2025-03-31'),
    (2025,  4, 'April 2025',     '2025-04-01', '2025-04-30'),
    (2025,  5, 'Mai 2025',       '2025-05-01', '2025-05-31'),
    (2025,  6, 'Juni 2025',      '2025-06-01', '2025-06-30'),
    (2025,  7, 'Juli 2025',      '2025-07-01', '2025-07-31'),
    (2025,  8, 'August 2025',    '2025-08-01', '2025-08-31'),
    (2025,  9, 'September 2025', '2025-09-01', '2025-09-30'),
    (2025, 10, 'Oktober 2025',   '2025-10-01', '2025-10-31'),
    (2025, 11, 'November 2025',  '2025-11-01', '2025-11-30'),
    (2025, 12, 'Dezember 2025',  '2025-12-01', '2025-12-31'),
    (2026,  1, 'Jänner 2026',    '2026-01-01', '2026-01-31'),
    (2026,  2, 'Februar 2026',   '2026-02-01', '2026-02-28'),
    (2026,  3, 'März 2026',      '2026-03-01', '2026-03-31'),
    (2026,  4, 'April 2026',     '2026-04-01', '2026-04-30'),
    (2026,  5, 'Mai 2026',       '2026-05-01', '2026-05-31'),
    (2026,  6, 'Juni 2026',      '2026-06-01', '2026-06-30'),
    (2026,  7, 'Juli 2026',      '2026-07-01', '2026-07-31'),
    (2026,  8, 'August 2026',    '2026-08-01', '2026-08-31'),
    (2026,  9, 'September 2026', '2026-09-01', '2026-09-30'),
    (2026, 10, 'Oktober 2026',   '2026-10-01', '2026-10-31'),
    (2026, 11, 'November 2026',  '2026-11-01', '2026-11-30'),
    (2026, 12, 'Dezember 2026',  '2026-12-01', '2026-12-31');

-- Vendors: leer — werden beim Onboarding oder automatisch beim ersten Beleg angelegt.

-- Initial audit event
INSERT INTO audit_log (event_type, entity_type, entity_id, actor, details)
VALUES ('system_init', 'system', 0, 'system', '{"version": "1.0", "description": "AP-Ledger initialisiert"}');
