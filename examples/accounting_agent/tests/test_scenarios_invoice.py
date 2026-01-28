"""
Invoice Test Scenarios for Accounting Agent

Comprehensive test cases covering:
- Incoming invoices (Eingangsrechnungen)
- Outgoing invoices (Ausgangsrechnungen)
- Domestic (Inland)
- EU Intra-community (Innergemeinschaftlich)
- Third country (Drittland - Schweiz)
- Various expense/revenue types

All invoices are §14 UStG compliant with required fields.
"""

import pytest
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class InvoiceDirection(str, Enum):
    """Invoice direction."""
    INCOMING = "incoming"  # Eingangsrechnung (Kreditor)
    OUTGOING = "outgoing"  # Ausgangsrechnung (Debitor)


class TaxType(str, Enum):
    """Tax treatment type."""
    DOMESTIC_19 = "domestic_19"  # Inland 19%
    DOMESTIC_7 = "domestic_7"  # Inland 7%
    REVERSE_CHARGE_EU = "reverse_charge_eu"  # EU Reverse Charge
    INTRA_COMMUNITY = "intra_community"  # Innergemeinschaftliche Lieferung
    EXPORT_THIRD_COUNTRY = "export_third_country"  # Ausfuhr Drittland
    IMPORT_THIRD_COUNTRY = "import_third_country"  # Einfuhr Drittland


@dataclass
class TestInvoice:
    """Test invoice data structure."""

    # Metadata
    scenario_id: str
    scenario_name: str
    direction: InvoiceDirection
    tax_type: TaxType

    # Supplier
    supplier_name: str
    supplier_address: str
    supplier_country: str
    supplier_vat_id: str

    # Recipient
    recipient_name: str
    recipient_address: str
    recipient_country: str
    recipient_vat_id: str

    # Invoice details
    invoice_number: str
    invoice_date: str
    delivery_date: str

    # Line items
    position_description: str
    net_amount: float
    vat_rate: float
    vat_amount: float
    gross_amount: float
    currency: str = "EUR"

    # Legal notice on invoice
    invoice_notice: Optional[str] = None

    # Expected results
    expected_compliant: bool = True
    expected_debit_account: Optional[str] = None
    expected_credit_account: Optional[str] = None
    expected_vat_account: Optional[str] = None
    expected_triggers_hitl: bool = False
    notes: str = ""

    def to_prompt(self) -> str:
        """Generate prompt for accounting agent."""
        direction_text = "Eingangsrechnung" if self.direction == InvoiceDirection.INCOMING else "Ausgangsrechnung"

        prompt = f"""Kontiere {direction_text}:
Lieferant: {self.supplier_name}, {self.supplier_address}, {self.supplier_country}, {self.supplier_vat_id}
Empfänger: {self.recipient_name}, {self.recipient_address}, {self.recipient_country}, {self.recipient_vat_id}
Rechnungsnummer: {self.invoice_number}
Rechnungsdatum: {self.invoice_date}
Liefer-/Leistungsdatum: {self.delivery_date}
Position: {self.position_description}
Nettobetrag: {self.net_amount:.2f} {self.currency}
MwSt {self.vat_rate:.0%}: {self.vat_amount:.2f} {self.currency}
Bruttobetrag: {self.gross_amount:.2f} {self.currency}"""

        if self.invoice_notice:
            prompt += f"\nRechnungshinweis: \"{self.invoice_notice}\""

        return prompt


# =============================================================================
# TEST SCENARIOS
# =============================================================================

# Our company (used as recipient for incoming, supplier for outgoing)
OUR_COMPANY = {
    "name": "TechSoft Solutions GmbH",
    "address": "Hauptstraße 42, 80331 München",
    "country": "DE",
    "vat_id": "USt-IdNr: DE987654321",
}

SCENARIOS: list[TestInvoice] = [
    # =========================================================================
    # INCOMING INVOICES (Eingangsrechnungen / Kreditorenbuchhaltung)
    # =========================================================================

    # --- Domestic (Inland) ---

    TestInvoice(
        scenario_id="IN-DE-001",
        scenario_name="Büromaterial Inland (gelernte Regel)",
        direction=InvoiceDirection.INCOMING,
        tax_type=TaxType.DOMESTIC_19,
        supplier_name="Büromarkt Böttcher AG",
        supplier_address="Friedrichstraße 123, 10117 Berlin",
        supplier_country="DE",
        supplier_vat_id="USt-IdNr: DE123456789",
        recipient_name=OUR_COMPANY["name"],
        recipient_address=OUR_COMPANY["address"],
        recipient_country=OUR_COMPANY["country"],
        recipient_vat_id=OUR_COMPANY["vat_id"],
        invoice_number="R-2026-00142",
        invoice_date="29.01.2026",
        delivery_date="28.01.2026",
        position_description="5x Druckertoner Brother TN-2420, Einzelpreis 39,90 EUR",
        net_amount=199.50,
        vat_rate=0.19,
        vat_amount=37.91,
        gross_amount=237.41,
        expected_compliant=True,
        expected_debit_account="4930",  # Bürobedarf (gelernte Regel!)
        expected_credit_account="1600",  # Verbindlichkeiten
        expected_vat_account="1576",  # Vorsteuer 19%
        notes="Sollte gelernte Vendor-Regel für Böttcher verwenden",
    ),

    TestInvoice(
        scenario_id="IN-DE-002",
        scenario_name="Consulting/Beratung Inland (hoher Betrag)",
        direction=InvoiceDirection.INCOMING,
        tax_type=TaxType.DOMESTIC_19,
        supplier_name="KPMG AG Wirtschaftsprüfungsgesellschaft",
        supplier_address="Klingelhöferstraße 18, 10785 Berlin",
        supplier_country="DE",
        supplier_vat_id="USt-IdNr: DE136751043",
        recipient_name=OUR_COMPANY["name"],
        recipient_address=OUR_COMPANY["address"],
        recipient_country=OUR_COMPANY["country"],
        recipient_vat_id=OUR_COMPANY["vat_id"],
        invoice_number="2026-MUC-004521",
        invoice_date="28.01.2026",
        delivery_date="Januar 2026",
        position_description="Steuerberatung und Jahresabschluss-Vorbereitung, 40 Stunden à 250 EUR",
        net_amount=10000.00,
        vat_rate=0.19,
        vat_amount=1900.00,
        gross_amount=11900.00,
        expected_compliant=True,
        expected_debit_account="4900",  # Fremdleistungen
        expected_credit_account="1600",
        expected_vat_account="1576",
        expected_triggers_hitl=True,  # Hoher Betrag > 5000 EUR
        notes="Hard Gate: high_amount sollte HITL triggern",
    ),

    TestInvoice(
        scenario_id="IN-DE-003",
        scenario_name="IT-Kosten/Software Inland",
        direction=InvoiceDirection.INCOMING,
        tax_type=TaxType.DOMESTIC_19,
        supplier_name="DATEV eG",
        supplier_address="Paumgartnerstraße 6-14, 90429 Nürnberg",
        supplier_country="DE",
        supplier_vat_id="USt-IdNr: DE133546770",
        recipient_name=OUR_COMPANY["name"],
        recipient_address=OUR_COMPANY["address"],
        recipient_country=OUR_COMPANY["country"],
        recipient_vat_id=OUR_COMPANY["vat_id"],
        invoice_number="DTV-2026-123456",
        invoice_date="01.01.2026",
        delivery_date="01.01.2026 - 31.12.2026",
        position_description="DATEV Unternehmen online, Jahresgebühr",
        net_amount=1200.00,
        vat_rate=0.19,
        vat_amount=228.00,
        gross_amount=1428.00,
        expected_compliant=True,
        expected_debit_account="4964",  # EDV-Kosten
        expected_credit_account="1600",
        expected_vat_account="1576",
        notes="IT-Kosten/Software-Abonnement",
    ),

    # --- EU Reverse Charge ---

    TestInvoice(
        scenario_id="IN-EU-001",
        scenario_name="Software-Subscription EU (Reverse Charge)",
        direction=InvoiceDirection.INCOMING,
        tax_type=TaxType.REVERSE_CHARGE_EU,
        supplier_name="Microsoft Ireland Operations Ltd",
        supplier_address="One Microsoft Place, South County Business Park, Leopardstown, Dublin 18",
        supplier_country="IE",
        supplier_vat_id="VAT: IE8256796U",
        recipient_name=OUR_COMPANY["name"],
        recipient_address=OUR_COMPANY["address"],
        recipient_country=OUR_COMPANY["country"],
        recipient_vat_id=OUR_COMPANY["vat_id"],
        invoice_number="INV-2026-EU-00891",
        invoice_date="01.02.2026",
        delivery_date="01.01.2026 - 31.12.2026",
        position_description="Microsoft 365 Business Premium, 10 Lizenzen Jahresabonnement",
        net_amount=1200.00,
        vat_rate=0.0,
        vat_amount=0.00,
        gross_amount=1200.00,
        invoice_notice="Reverse charge - VAT to be accounted for by the recipient pursuant to Article 196 Council Directive 2006/112/EC",
        expected_compliant=True,
        expected_debit_account="4964",  # EDV-Kosten
        expected_credit_account="1600",
        expected_vat_account="1577",  # Vorsteuer EU + 1787 USt EU (stornierend)
        notes="Reverse Charge: VSt und USt EU buchen (steuerneutral)",
    ),

    TestInvoice(
        scenario_id="IN-EU-002",
        scenario_name="Cloud Services EU (Reverse Charge)",
        direction=InvoiceDirection.INCOMING,
        tax_type=TaxType.REVERSE_CHARGE_EU,
        supplier_name="Amazon Web Services EMEA SARL",
        supplier_address="38 Avenue John F. Kennedy, L-1855 Luxembourg",
        supplier_country="LU",
        supplier_vat_id="VAT: LU26888617",
        recipient_name=OUR_COMPANY["name"],
        recipient_address=OUR_COMPANY["address"],
        recipient_country=OUR_COMPANY["country"],
        recipient_vat_id=OUR_COMPANY["vat_id"],
        invoice_number="AWS-2026-LU-789012",
        invoice_date="01.02.2026",
        delivery_date="Januar 2026",
        position_description="AWS Cloud Services (EC2, S3, RDS) Januar 2026",
        net_amount=2850.00,
        vat_rate=0.0,
        vat_amount=0.00,
        gross_amount=2850.00,
        invoice_notice="Reverse charge - VAT to be paid by the customer",
        expected_compliant=True,
        expected_debit_account="4964",  # EDV-Kosten
        expected_credit_account="1600",
        expected_vat_account="1577",
        notes="AWS EU - Reverse Charge",
    ),

    # --- Third Country (Drittland) ---

    TestInvoice(
        scenario_id="IN-CH-001",
        scenario_name="Dienstleistung Schweiz (Drittland Import)",
        direction=InvoiceDirection.INCOMING,
        tax_type=TaxType.IMPORT_THIRD_COUNTRY,
        supplier_name="Swisscom (Schweiz) AG",
        supplier_address="Alte Tiefenaustrasse 6, 3048 Worblaufen",
        supplier_country="CH",
        supplier_vat_id="UID: CHE-101.654.423 MWST",
        recipient_name=OUR_COMPANY["name"],
        recipient_address=OUR_COMPANY["address"],
        recipient_country=OUR_COMPANY["country"],
        recipient_vat_id=OUR_COMPANY["vat_id"],
        invoice_number="CH-2026-789012",
        invoice_date="31.01.2026",
        delivery_date="Januar 2026",
        position_description="Mobile Business Roaming Services Europa",
        net_amount=450.00,
        vat_rate=0.0,
        vat_amount=0.00,
        gross_amount=450.00,
        currency="CHF",
        invoice_notice="Export - keine Schweizer MWST",
        expected_compliant=True,
        expected_debit_account="4920",  # Telekommunikation
        expected_credit_account="1600",
        notes="Schweiz Drittland - ggf. Einfuhrumsatzsteuer",
    ),

    # =========================================================================
    # OUTGOING INVOICES (Ausgangsrechnungen / Debitorenbuchhaltung)
    # =========================================================================

    # --- Domestic (Inland) ---

    TestInvoice(
        scenario_id="OUT-DE-001",
        scenario_name="SaaS-Subscription Umsatz Inland",
        direction=InvoiceDirection.OUTGOING,
        tax_type=TaxType.DOMESTIC_19,
        supplier_name=OUR_COMPANY["name"],
        supplier_address=OUR_COMPANY["address"],
        supplier_country=OUR_COMPANY["country"],
        supplier_vat_id=OUR_COMPANY["vat_id"],
        recipient_name="Siemens AG",
        recipient_address="Werner-von-Siemens-Straße 1, 80333 München",
        recipient_country="DE",
        recipient_vat_id="USt-IdNr: DE129274202",
        invoice_number="AR-2026-00015",
        invoice_date="01.01.2026",
        delivery_date="Q1/2026 (01.01. - 31.03.2026)",
        position_description="SaaS Enterprise Subscription, 50 User x 3 Monate x 33,33 EUR",
        net_amount=5000.00,
        vat_rate=0.19,
        vat_amount=950.00,
        gross_amount=5950.00,
        expected_compliant=True,
        expected_debit_account="1200",  # Forderungen
        expected_credit_account="8400",  # Erlöse 19%
        expected_vat_account="1776",  # USt 19%
        notes="Standard Inlands-Umsatz",
    ),

    TestInvoice(
        scenario_id="OUT-DE-002",
        scenario_name="Consulting Umsatz Inland",
        direction=InvoiceDirection.OUTGOING,
        tax_type=TaxType.DOMESTIC_19,
        supplier_name=OUR_COMPANY["name"],
        supplier_address=OUR_COMPANY["address"],
        supplier_country=OUR_COMPANY["country"],
        supplier_vat_id=OUR_COMPANY["vat_id"],
        recipient_name="BMW AG",
        recipient_address="Petuelring 130, 80809 München",
        recipient_country="DE",
        recipient_vat_id="USt-IdNr: DE129382628",
        invoice_number="AR-2026-00022",
        invoice_date="25.01.2026",
        delivery_date="Januar 2026",
        position_description="Implementierungsberatung Cloud-Migration, 40 Stunden à 300 EUR",
        net_amount=12000.00,
        vat_rate=0.19,
        vat_amount=2280.00,
        gross_amount=14280.00,
        expected_compliant=True,
        expected_debit_account="1200",
        expected_credit_account="8400",
        expected_vat_account="1776",
        expected_triggers_hitl=True,  # Hoher Betrag
        notes="Consulting-Erlöse, hoher Betrag > 5000 EUR",
    ),

    # --- EU Intra-Community ---

    TestInvoice(
        scenario_id="OUT-EU-001",
        scenario_name="Partner-Lizenz EU (ig. Lieferung)",
        direction=InvoiceDirection.OUTGOING,
        tax_type=TaxType.INTRA_COMMUNITY,
        supplier_name=OUR_COMPANY["name"],
        supplier_address=OUR_COMPANY["address"],
        supplier_country=OUR_COMPANY["country"],
        supplier_vat_id=OUR_COMPANY["vat_id"],
        recipient_name="Philips Electronics Nederland BV",
        recipient_address="Amstelplein 2, 1096 BC Amsterdam",
        recipient_country="NL",
        recipient_vat_id="VAT: NL123456789B01",
        invoice_number="AR-2026-EU-00003",
        invoice_date="01.01.2026",
        delivery_date="Q1/2026",
        position_description="Partner Software License Fee Q1/2026",
        net_amount=3500.00,
        vat_rate=0.0,
        vat_amount=0.00,
        gross_amount=3500.00,
        invoice_notice="Steuerfreie innergemeinschaftliche Lieferung gem. §4 Nr. 1b UStG i.V.m. §6a UStG",
        expected_compliant=True,
        expected_debit_account="1200",
        expected_credit_account="8125",  # Steuerfreie ig. Lieferungen
        notes="EU B2B - steuerfrei mit Meldung ZM",
    ),

    TestInvoice(
        scenario_id="OUT-EU-002",
        scenario_name="Consulting B2B EU (sonstige Leistung)",
        direction=InvoiceDirection.OUTGOING,
        tax_type=TaxType.INTRA_COMMUNITY,
        supplier_name=OUR_COMPANY["name"],
        supplier_address=OUR_COMPANY["address"],
        supplier_country=OUR_COMPANY["country"],
        supplier_vat_id=OUR_COMPANY["vat_id"],
        recipient_name="SAP France SAS",
        recipient_address="35 rue d'Alsace, 92300 Levallois-Perret",
        recipient_country="FR",
        recipient_vat_id="VAT: FR84379769545",
        invoice_number="AR-2026-FR-00002",
        invoice_date="31.01.2026",
        delivery_date="Januar 2026",
        position_description="Remote Consulting Services, Integration Support, 20 Stunden à 300 EUR",
        net_amount=6000.00,
        vat_rate=0.0,
        vat_amount=0.00,
        gross_amount=6000.00,
        invoice_notice="Steuerschuldnerschaft des Leistungsempfängers gem. §13b UStG - Ort der sonstigen Leistung gem. §3a Abs. 2 UStG beim Empfänger",
        expected_compliant=True,
        expected_debit_account="1200",
        expected_credit_account="8336",  # Erlöse sonstige Leistungen EU
        expected_triggers_hitl=True,  # Hoher Betrag
        notes="Sonstige Leistung B2B EU - Reverse Charge beim Empfänger",
    ),

    # --- Third Country Export (Drittland) ---

    TestInvoice(
        scenario_id="OUT-CH-001",
        scenario_name="Weiterverrechnung Tecan Schweiz (Export)",
        direction=InvoiceDirection.OUTGOING,
        tax_type=TaxType.EXPORT_THIRD_COUNTRY,
        supplier_name=OUR_COMPANY["name"],
        supplier_address=OUR_COMPANY["address"],
        supplier_country=OUR_COMPANY["country"],
        supplier_vat_id=OUR_COMPANY["vat_id"],
        recipient_name="Tecan Group AG",
        recipient_address="Seestrasse 103, 8708 Männedorf",
        recipient_country="CH",
        recipient_vat_id="UID: CHE-105.775.974 MWST",
        invoice_number="AR-2026-CH-00001",
        invoice_date="31.01.2026",
        delivery_date="Januar 2026",
        position_description="Weiterverrechnung IT-Infrastruktur und Softwarelizenzen Januar 2026",
        net_amount=8500.00,
        vat_rate=0.0,
        vat_amount=0.00,
        gross_amount=8500.00,
        invoice_notice="Steuerfreie Ausfuhrlieferung gem. §4 Nr. 1a UStG i.V.m. §6 UStG",
        expected_compliant=True,
        expected_debit_account="1200",
        expected_credit_account="8120",  # Steuerfreie Ausfuhrlieferungen
        expected_triggers_hitl=True,  # Hoher Betrag
        notes="Export Schweiz - steuerfrei",
    ),

    TestInvoice(
        scenario_id="OUT-CH-002",
        scenario_name="SaaS-Subscription Schweiz (Export)",
        direction=InvoiceDirection.OUTGOING,
        tax_type=TaxType.EXPORT_THIRD_COUNTRY,
        supplier_name=OUR_COMPANY["name"],
        supplier_address=OUR_COMPANY["address"],
        supplier_country=OUR_COMPANY["country"],
        supplier_vat_id=OUR_COMPANY["vat_id"],
        recipient_name="Roche Holding AG",
        recipient_address="Grenzacherstrasse 124, 4070 Basel",
        recipient_country="CH",
        recipient_vat_id="UID: CHE-105.841.505 MWST",
        invoice_number="AR-2026-CH-00005",
        invoice_date="01.02.2026",
        delivery_date="Q1/2026",
        position_description="SaaS Professional Subscription, 25 User, Quartal",
        net_amount=2500.00,
        vat_rate=0.0,
        vat_amount=0.00,
        gross_amount=2500.00,
        invoice_notice="Steuerfreie Ausfuhrlieferung gem. §4 Nr. 1a UStG",
        expected_compliant=True,
        expected_debit_account="1200",
        expected_credit_account="8120",
        notes="Export Schweiz - Software als Dienstleistung",
    ),
]


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

class TestInvoiceScenarios:
    """Test class for invoice scenarios."""

    @pytest.fixture
    def scenarios(self) -> list[TestInvoice]:
        """Return all test scenarios."""
        return SCENARIOS

    def test_all_scenarios_have_required_fields(self, scenarios: list[TestInvoice]):
        """Verify all scenarios have required invoice fields."""
        for scenario in scenarios:
            assert scenario.supplier_name, f"{scenario.scenario_id}: Missing supplier_name"
            assert scenario.supplier_vat_id, f"{scenario.scenario_id}: Missing supplier_vat_id"
            assert scenario.recipient_name, f"{scenario.scenario_id}: Missing recipient_name"
            assert scenario.invoice_number, f"{scenario.scenario_id}: Missing invoice_number"
            assert scenario.invoice_date, f"{scenario.scenario_id}: Missing invoice_date"
            assert scenario.net_amount > 0, f"{scenario.scenario_id}: Invalid net_amount"

    def test_vat_calculation_correct(self, scenarios: list[TestInvoice]):
        """Verify VAT calculations are mathematically correct."""
        for scenario in scenarios:
            if scenario.vat_rate > 0:
                expected_vat = round(scenario.net_amount * scenario.vat_rate, 2)
                assert abs(scenario.vat_amount - expected_vat) < 0.02, \
                    f"{scenario.scenario_id}: VAT mismatch. Expected {expected_vat}, got {scenario.vat_amount}"

                expected_gross = scenario.net_amount + scenario.vat_amount
                assert abs(scenario.gross_amount - expected_gross) < 0.02, \
                    f"{scenario.scenario_id}: Gross mismatch. Expected {expected_gross}, got {scenario.gross_amount}"

    def test_reverse_charge_has_notice(self, scenarios: list[TestInvoice]):
        """Verify Reverse Charge invoices have required notice."""
        for scenario in scenarios:
            if scenario.tax_type == TaxType.REVERSE_CHARGE_EU:
                assert scenario.invoice_notice is not None, \
                    f"{scenario.scenario_id}: Reverse Charge requires invoice notice"
                assert "reverse charge" in scenario.invoice_notice.lower() or \
                       "steuerschuldnerschaft" in scenario.invoice_notice.lower(), \
                    f"{scenario.scenario_id}: Reverse Charge notice must mention RC"

    def test_eu_export_has_notice(self, scenarios: list[TestInvoice]):
        """Verify EU intra-community invoices have required notice."""
        for scenario in scenarios:
            if scenario.tax_type == TaxType.INTRA_COMMUNITY:
                assert scenario.invoice_notice is not None, \
                    f"{scenario.scenario_id}: EU ig. Lieferung requires invoice notice"

    def test_third_country_export_has_notice(self, scenarios: list[TestInvoice]):
        """Verify third country exports have required notice."""
        for scenario in scenarios:
            if scenario.tax_type == TaxType.EXPORT_THIRD_COUNTRY:
                assert scenario.invoice_notice is not None, \
                    f"{scenario.scenario_id}: Export requires invoice notice"
                assert "§4" in scenario.invoice_notice or "steuerfrei" in scenario.invoice_notice.lower(), \
                    f"{scenario.scenario_id}: Export notice must reference §4 UStG"

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.scenario_id)
    def test_prompt_generation(self, scenario: TestInvoice):
        """Test that prompts are generated correctly."""
        prompt = scenario.to_prompt()

        assert scenario.supplier_name in prompt
        assert scenario.invoice_number in prompt
        assert str(scenario.net_amount) in prompt or f"{scenario.net_amount:.2f}" in prompt

        if scenario.invoice_notice:
            assert scenario.invoice_notice in prompt


# =============================================================================
# CLI RUNNER
# =============================================================================

def print_scenario_summary():
    """Print a summary of all test scenarios."""
    print("\n" + "=" * 80)
    print("INVOICE TEST SCENARIOS")
    print("=" * 80)

    incoming = [s for s in SCENARIOS if s.direction == InvoiceDirection.INCOMING]
    outgoing = [s for s in SCENARIOS if s.direction == InvoiceDirection.OUTGOING]

    print(f"\nTotal scenarios: {len(SCENARIOS)}")
    print(f"  - Incoming (Eingangsrechnungen): {len(incoming)}")
    print(f"  - Outgoing (Ausgangsrechnungen): {len(outgoing)}")

    print("\n" + "-" * 80)
    print("INCOMING INVOICES (Kreditorenbuchhaltung)")
    print("-" * 80)
    for s in incoming:
        hitl = " [HITL]" if s.expected_triggers_hitl else ""
        print(f"  {s.scenario_id}: {s.scenario_name}{hitl}")
        print(f"    Supplier: {s.supplier_name} ({s.supplier_country})")
        print(f"    Amount: {s.gross_amount:.2f} {s.currency}")
        print(f"    Tax: {s.tax_type.value}")
        print()

    print("-" * 80)
    print("OUTGOING INVOICES (Debitorenbuchhaltung)")
    print("-" * 80)
    for s in outgoing:
        hitl = " [HITL]" if s.expected_triggers_hitl else ""
        print(f"  {s.scenario_id}: {s.scenario_name}{hitl}")
        print(f"    Customer: {s.recipient_name} ({s.recipient_country})")
        print(f"    Amount: {s.gross_amount:.2f} {s.currency}")
        print(f"    Tax: {s.tax_type.value}")
        print()


def print_prompts_for_testing():
    """Print all prompts ready for copy-paste testing."""
    print("\n" + "=" * 80)
    print("PROMPTS FOR MANUAL TESTING")
    print("=" * 80)
    print("\nCopy and paste these into the accounting agent chat:\n")
    print("taskforce chat --plugin examples/accounting_agent --profile accounting_agent --lean")
    print()

    for i, scenario in enumerate(SCENARIOS, 1):
        print("-" * 80)
        print(f"SCENARIO {i}/{len(SCENARIOS)}: {scenario.scenario_id} - {scenario.scenario_name}")
        print(f"Expected: Debit {scenario.expected_debit_account} | Credit {scenario.expected_credit_account}")
        if scenario.expected_triggers_hitl:
            print(">>> EXPECTS HITL REVIEW <<<")
        print("-" * 80)
        print()
        print(scenario.to_prompt())
        print()
        print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--prompts":
        print_prompts_for_testing()
    else:
        print_scenario_summary()
        print("\nRun with --prompts to see copy-paste ready test prompts")
        print("Run with pytest to execute unit tests")
