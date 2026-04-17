# Exploratory Test Plan — <AGENT NAME>

**Scope:** <What phase / feature slice of the agent this plan covers.>
**Default-Setup pro Szenario:** <How a fresh test environment is created —
e.g. "frischer Kunde via provision_customer.py, Country AT, heute =
2026-04-17". Stays constant across scenarios unless a scenario
explicitly overrides it.>

Status-Legende: `[ ]` offen · `[x]` durchlaufen (Ergebnis im Report) · `[!]` Blocker (stopt Loop).

---

## 1 <Section title — e.g. Happy Path>

- [ ] **S01 — <Kurztitel>.** <1-Satz-Beschreibung was der Nutzer / das
  System tut.>
  **Expected:** <messbar — z.B. "Genau 1 `invoices`-Row, `status=posted`,
  `total_gross=186.00`. Agent-Reply enthält 'gebucht'. Kein Crash.">

- [ ] **S02 — <Kurztitel>.** <…>
  **Expected:** <…>

## 2 <Section title — e.g. Reports / Edge Amounts / Concurrency>

- [ ] **S03 — <Kurztitel>.** <…>
  **Expected:** <…>

---

## Round 2 (expand after Round 1 is clean)

Ideas to revisit once the above is all green:

- <Edge case / tricky scenario 1>
- <Edge case 2>
- <…>

---

## Configuration notes

- <Which env vars the harness needs, e.g. AZURE_API_KEY.>
- <Where state lives during a test, e.g. `%TEMP%/<slug>/`.>
- <Any external dependencies — Telegram, a real database, network calls.>

## Writing good scenarios

- **One behaviour per scenario.** If you need 3 bullets under Expected,
  split the scenario.
- **Setup in a single line.** If you need multi-step setup, put it in
  the harness as a fixture, not in the scenario text.
- **Expected must be assertable.** "Looks right" doesn't count.
  "Total gross == 186.00 AND status == posted" does.
- **Keep Round 1 to 6-10 scenarios.** You can always expand after the
  first pass. Too many scenarios up front = the loop hits the 15-iter
  cap before surfacing interesting bugs.
