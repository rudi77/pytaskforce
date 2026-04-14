-- =============================================================================
-- Seed-Daten: Deutsche Friseurin / Einzelunternehmen (EÜR)
-- Kontenrahmen: SKR03
-- =============================================================================

-- Steuersätze Deutschland
INSERT OR IGNORE INTO tax_codes (code, rate, label, description) VALUES
    ('DE_19',   0.19, '19% USt',  'Regelsteuersatz Deutschland'),
    ('DE_7',    0.07, '7% USt',   'Ermäßigter Steuersatz (Lebensmittel, Bücher, ÖPNV)'),
    ('DE_0',    0.00, '0% USt',   'Steuerbefreit (Versicherung, Miete Wohnung, Ärzte)'),
    ('EU_RC',   0.00, 'Reverse Charge', 'Innergemeinschaftlicher Erwerb / Reverse Charge');

-- Einnahmen-Kategorien
INSERT OR IGNORE INTO categories (code, name, type, description, default_tax_code, sort_order) VALUES
    ('einnahmen_bar',       'Bareinnahmen',           'revenue', 'Tageslosung / Kasseneinnahmen', 'DE_19', 10),
    ('einnahmen_karte',     'Karteneinnahmen',        'revenue', 'EC-Karte / Kreditkarte',        'DE_19', 20),
    ('einnahmen_gutschein', 'Gutschein-Einlösung',    'revenue', 'Eingelöste Gutscheine',         'DE_19', 30),
    ('einnahmen_sonstige',  'Sonstige Einnahmen',     'revenue', 'Trinkgeld, Provisionen etc.',   'DE_19', 40);

-- Ausgaben-Kategorien (Friseur-spezifisch)
INSERT OR IGNORE INTO categories (code, name, type, description, default_tax_code, sort_order) VALUES
    ('waren_farbe',         'Haarfarben & Chemie',    'expense', 'Colorationen, Blondierung, Dauerwelle',    'DE_19', 100),
    ('waren_pflege',        'Pflegeprodukte',         'expense', 'Shampoo, Conditioner, Kur, Styling',       'DE_19', 110),
    ('waren_verbrauch',     'Verbrauchsmaterial',      'expense', 'Handschuhe, Alufolie, Umhänge, Handtücher','DE_19', 120),
    ('waren_verkauf',       'Verkaufsware',           'expense', 'Produkte zum Weiterverkauf an Kunden',     'DE_19', 130),
    ('miete',               'Miete Geschäftslokal',   'expense', 'Geschäftsraummiete',            'DE_19', 200),
    ('betriebskosten',      'Betriebskosten',         'expense', 'Strom, Wasser, Heizung, Müll',  'DE_19', 210),
    ('versicherung',        'Versicherungen',         'expense', 'Betriebshaftpflicht, Inventar', 'DE_0',  220),
    ('telefon_internet',    'Telefon & Internet',     'expense', 'Festnetz, Mobil, Internet',     'DE_19', 230),
    ('werbung',             'Werbung & Marketing',    'expense', 'Visitenkarten, Social Media',   'DE_19', 240),
    ('fortbildung',         'Fortbildung',            'expense', 'Seminare, Kurse, Messen',       'DE_19', 250),
    ('geraete',             'Geräte & Werkzeug',      'expense', 'Schere, Föhn, Glätteisen',      'DE_19', 260),
    ('einrichtung',         'Einrichtung & Ausstattung','expense','Möbel, Spiegel, Waschplatz',   'DE_19', 270),
    ('buero',               'Bürobedarf',             'expense', 'Papier, Druckerpatronen, Ordner','DE_19', 280),
    ('kfz',                 'KFZ-Kosten',             'expense', 'Betriebliche Fahrten, Tanken',  'DE_19', 290),
    ('bank',                'Bankgebühren',           'expense', 'Kontoführung, Kartengebühren',  'DE_0',  300),
    ('steuerberater',       'Steuerberatung',         'expense', 'Steuerberater, Buchhaltung',    'DE_19', 310),
    ('reinigung',           'Reinigung',              'expense', 'Reinigungsmittel, Putzdienst',  'DE_19', 320),
    ('sonstige_ausgaben',   'Sonstige Ausgaben',      'expense', 'Nicht zuordenbare Ausgaben',    'DE_19', 900);

-- Geschäftsperioden 2025 & 2026
INSERT OR IGNORE INTO fiscal_periods (year, month, label, start_date, end_date) VALUES
    (2025,  1, 'Januar 2025',    '2025-01-01', '2025-01-31'),
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
    (2026,  1, 'Januar 2026',    '2026-01-01', '2026-01-31'),
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

-- Typische Lieferanten (Deutschland)
INSERT OR IGNORE INTO vendors (name, name_normalized, default_category_code, default_tax_code, match_keywords) VALUES
    ('Wella Deutschland',       'wella deutschland',       'waren_farbe',    'DE_19', 'wella,wella deutschland,wella germany'),
    ('L''Oréal Professionnel',  'l''oréal professionnel',  'waren_farbe',    'DE_19', 'loreal,l''oreal,professionnel,l''oréal'),
    ('Schwarzkopf Professional','schwarzkopf professional','waren_farbe',    'DE_19', 'schwarzkopf,henkel'),
    ('Goldwell',                'goldwell',                'waren_farbe',    'DE_19', 'goldwell,kao'),
    ('Redken',                  'redken',                  'waren_pflege',   'DE_19', 'redken'),
    ('Friseur-Großhandel',      'friseur-großhandel',      'waren_verbrauch','DE_19', 'friseur-grosshandel,friseurgroßhandel,coiffeur'),
    ('METRO',                   'metro',                   'waren_verbrauch','DE_19', 'metro,metro cash'),
    ('Amazon',                  'amazon',                  'buero',          'DE_19', 'amazon,amzn'),
    ('Deutsche Telekom',        'deutsche telekom',        'telefon_internet','DE_19','telekom,deutsche telekom,t-mobile,magenta'),
    ('Allianz Versicherung',    'allianz versicherung',    'versicherung',  'DE_0',  'allianz'),
    ('AXA Versicherung',        'axa versicherung',        'versicherung',  'DE_0',  'axa'),
    ('Stadtwerke',              'stadtwerke',              'betriebskosten','DE_19',  'stadtwerke,swm,swb'),
    ('E.ON',                    'e.on',                    'betriebskosten','DE_19',  'e.on,eon,innogy'),
    ('Lidl',                    'lidl',                    'reinigung',     'DE_19',  'lidl'),
    ('DM Drogeriemarkt',        'dm drogeriemarkt',        'reinigung',     'DE_19',  'dm,dm drogeriemarkt,drogerie markt'),
    ('Deutsche Post DHL',       'deutsche post dhl',       'buero',         'DE_19',  'post,deutsche post,dhl');

-- Initial audit event
INSERT INTO audit_log (event_type, entity_type, entity_id, actor, details)
VALUES ('system_init', 'system', 0, 'system', '{"version": "1.0", "country": "DE", "description": "AP-Ledger initialisiert (Deutschland)"}');
