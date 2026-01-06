"""
Accounting Domain Models

This module defines the core domain models for German accounting operations:
- Invoice: Represents a parsed invoice with all relevant fields
- LineItem: Individual line items within an invoice
- BookingProposal: Suggested booking entries (Buchungsvorschlag)
- ComplianceFields: Fields required for compliance checking
- ComplianceResult: Result of compliance validation
- ComplianceWarning/Error: Specific compliance issues

These models are pure domain objects with no infrastructure dependencies.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class LineItem:
    """
    Individual line item within an invoice.

    Attributes:
        description: Item description text
        quantity: Number of units
        unit_price: Price per unit (net)
        net_amount: Total net amount for this line
        vat_rate: VAT rate applicable (e.g., 0.19, 0.07)
        vat_amount: Calculated VAT amount
        account_suggestion: Suggested account number (optional)
    """

    description: str
    quantity: Decimal
    unit_price: Decimal
    net_amount: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    account_suggestion: Optional[str] = None


@dataclass
class ComplianceFields:
    """
    Fields required for compliance checking per §14 UStG.

    Attributes:
        has_supplier_name: Supplier name present
        has_supplier_address: Supplier address present
        has_supplier_vat_id: Supplier VAT ID present
        has_recipient_name: Recipient name present
        has_recipient_address: Recipient address present
        has_invoice_number: Invoice number present
        has_invoice_date: Invoice date present
        has_delivery_date: Delivery/service date present
        has_quantity_description: Quantity and description present
        has_net_amount: Net amount present
        has_vat_rate: VAT rate present
        has_vat_amount: VAT amount present
        has_gross_amount: Gross amount present
    """

    has_supplier_name: bool = False
    has_supplier_address: bool = False
    has_supplier_vat_id: bool = False
    has_recipient_name: bool = False
    has_recipient_address: bool = False
    has_invoice_number: bool = False
    has_invoice_date: bool = False
    has_delivery_date: bool = False
    has_quantity_description: bool = False
    has_net_amount: bool = False
    has_vat_rate: bool = False
    has_vat_amount: bool = False
    has_gross_amount: bool = False


@dataclass
class Invoice:
    """
    Parsed invoice with all relevant fields for German accounting.

    Represents a complete invoice document with supplier information,
    amounts, line items, and compliance-relevant fields.

    Attributes:
        invoice_id: Internal unique identifier
        supplier_name: Name of the supplier/vendor
        supplier_address: Full supplier address
        supplier_vat_id: Supplier's VAT identification number (USt-IdNr.)
        recipient_name: Name of the recipient
        recipient_address: Full recipient address
        invoice_number: Supplier's invoice number (Rechnungsnummer)
        invoice_date: Date of invoice issuance
        delivery_date: Date of delivery/service (Lieferdatum)
        total_gross: Total amount including VAT
        total_net: Total amount excluding VAT
        total_vat: Total VAT amount
        line_items: List of individual line items
        compliance_fields: Compliance check fields
        confidence_score: Extraction confidence (0.0 to 1.0)
        raw_text: Original extracted text (for debugging)
        currency: Currency code (default: EUR)
    """

    invoice_id: str
    supplier_name: str
    invoice_number: str
    invoice_date: date
    total_gross: Decimal
    total_net: Decimal
    total_vat: Decimal
    line_items: list[LineItem] = field(default_factory=list)
    compliance_fields: ComplianceFields = field(default_factory=ComplianceFields)
    confidence_score: float = 0.0
    supplier_address: Optional[str] = None
    supplier_vat_id: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_address: Optional[str] = None
    delivery_date: Optional[date] = None
    raw_text: Optional[str] = None
    currency: str = "EUR"


@dataclass
class BookingProposal:
    """
    Proposed booking entry (Buchungsvorschlag).

    Represents a suggested double-entry bookkeeping entry with
    debit and credit accounts, amounts, and legal basis.

    Attributes:
        debit_account: Debit account number (Soll-Konto)
        debit_account_name: Human-readable account name
        credit_account: Credit account number (Haben-Konto)
        credit_account_name: Human-readable account name
        amount: Booking amount
        vat_account: VAT account number (Vorsteuer-Konto)
        vat_amount: VAT amount to book
        description: Booking description (Buchungstext)
        legal_basis: Legal reference (e.g., "§4 Nr. 1a UStG")
        explanation: Detailed explanation of the booking
        confidence: Confidence score for this proposal (0.0 to 1.0)
    """

    debit_account: str
    credit_account: str
    amount: Decimal
    description: str
    legal_basis: str
    explanation: str
    debit_account_name: Optional[str] = None
    credit_account_name: Optional[str] = None
    vat_account: Optional[str] = None
    vat_amount: Optional[Decimal] = None
    confidence: float = 1.0


@dataclass
class ComplianceWarning:
    """
    Non-critical compliance warning.

    Attributes:
        field: Field name that triggered the warning
        message: Warning message in German
        legal_reference: Relevant legal reference
        severity: Warning severity (low, medium)
    """

    field: str
    message: str
    legal_reference: str
    severity: str = "low"


@dataclass
class ComplianceError:
    """
    Critical compliance error (Pflichtangabe fehlt).

    Attributes:
        field: Field name that is missing/invalid
        message: Error message in German
        legal_reference: Relevant legal reference (e.g., "§14 Abs. 4 Nr. 1 UStG")
    """

    field: str
    message: str
    legal_reference: str


@dataclass
class ComplianceResult:
    """
    Result of compliance validation against §14 UStG.

    Attributes:
        is_compliant: True if invoice meets all requirements
        missing_fields: List of missing mandatory field names
        warnings: List of non-critical compliance warnings
        errors: List of critical compliance errors
        legal_basis: Primary legal reference for the check
        is_small_invoice: True if invoice qualifies as Kleinbetragsrechnung
        small_invoice_threshold: Threshold amount for small invoice (§33 UStDV)
    """

    is_compliant: bool
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[ComplianceWarning] = field(default_factory=list)
    errors: list[ComplianceError] = field(default_factory=list)
    legal_basis: str = "§14 Abs. 4 UStG"
    is_small_invoice: bool = False
    small_invoice_threshold: Decimal = Decimal("250.00")
