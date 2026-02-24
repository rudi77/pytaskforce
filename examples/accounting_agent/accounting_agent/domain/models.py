"""
Accounting Domain Models

This module defines the core domain models for German accounting operations:
- Invoice: Represents a parsed invoice with all relevant fields
- LineItem: Individual line items within an invoice
- BookingProposal: Suggested booking entries (Buchungsvorschlag)
- ComplianceFields: Fields required for compliance checking
- ComplianceResult: Result of compliance validation
- ComplianceWarning/Error: Specific compliance issues
- AccountingRule: Rule for semantic account assignment
- RuleMatch: Result of rule matching with similarity score
- ConfidenceResult: Result of confidence evaluation
- WorkflowState: Current state of invoice processing workflow

These models are pure domain objects with no infrastructure dependencies.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
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


# =============================================================================
# Semantic Rules Engine Models (PRD Phase 1)
# =============================================================================


class RuleType(str, Enum):
    """Type of accounting rule."""

    VENDOR_ONLY = "vendor_only"  # Match by vendor name only
    VENDOR_ITEM = "vendor_item"  # Match by vendor + item semantics


class RuleSource(str, Enum):
    """Source/origin of a rule."""

    MANUAL = "manual"  # Manually created rule
    AUTO_HIGH_CONFIDENCE = "auto_high_confidence"  # Auto-generated from high-confidence booking
    HITL_CORRECTION = "hitl_correction"  # Created from HITL correction


class MatchType(str, Enum):
    """Type of rule match."""

    EXACT = "exact"  # Exact string match
    SEMANTIC = "semantic"  # Semantic similarity match
    VENDOR_GENERALIZED = "vendor_generalized"  # Inferred from vendor-level rule pattern


class ConfidenceRecommendation(str, Enum):
    """Recommendation based on confidence evaluation."""

    AUTO_BOOK = "auto_book"  # Confidence high enough for automatic booking
    HITL_REVIEW = "hitl_review"  # Requires human-in-the-loop review


@dataclass
class VendorAccountProfile:
    """Vendor-level account distribution derived from learned rules.

    When a vendor has enough learned rules pointing to the same account,
    this profile enables generalization to new, unseen items from the same vendor.

    Attributes:
        vendor_pattern: The vendor pattern these rules share
        dominant_account: Most frequently assigned account number
        dominant_account_name: Human-readable account name
        total_rules: Total number of learned rules for this vendor
        rules_for_dominant: How many rules point to dominant_account
        dominance_ratio: rules_for_dominant / total_rules (0.0-1.0)
        all_item_patterns: All known item patterns from this vendor's rules
    """

    vendor_pattern: str
    dominant_account: str
    dominant_account_name: Optional[str]
    total_rules: int
    rules_for_dominant: int
    dominance_ratio: float
    all_item_patterns: list[str] = field(default_factory=list)


@dataclass
class AccountingRule:
    """
    Rule for deterministic or semantic account assignment.

    Supports two rule types:
    - vendor_only: Maps vendor directly to target account
    - vendor_item: Maps vendor + item patterns to target account using embeddings

    Attributes:
        rule_id: Unique identifier for the rule
        rule_type: Type of rule (vendor_only or vendor_item)
        vendor_pattern: Regex pattern or exact name to match vendor
        item_patterns: List of item description patterns (for vendor_item rules)
        target_account: Target account number (e.g., "4930")
        target_account_name: Human-readable account name
        priority: Rule priority (higher = checked first)
        similarity_threshold: Minimum similarity score for semantic matches (0.0-1.0)
        source: Origin of the rule (manual, auto, or HITL)
        version: Rule version number for auditing
        is_active: Whether the rule is currently active
        legal_basis: Legal reference for the account assignment
        created_at: ISO timestamp of rule creation
        updated_at: ISO timestamp of last update
    """

    rule_id: str
    rule_type: RuleType
    vendor_pattern: str
    target_account: str
    priority: int = 100
    item_patterns: list[str] = field(default_factory=list)
    target_account_name: Optional[str] = None
    similarity_threshold: float = 0.8
    source: RuleSource = RuleSource.MANUAL
    version: int = 1
    is_active: bool = True
    legal_basis: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class RuleMatch:
    """
    Result of matching an invoice/line item against accounting rules.

    Attributes:
        rule: The matched accounting rule
        match_type: Type of match (exact or semantic)
        similarity_score: Similarity score for semantic matches (0.0-1.0)
        matched_item_pattern: The specific item pattern that matched (for vendor_item rules)
        is_ambiguous: True if multiple rules matched with similar scores
        alternative_matches: List of alternative rule matches if ambiguous
    """

    rule: AccountingRule
    match_type: MatchType
    similarity_score: float
    matched_item_pattern: Optional[str] = None
    is_ambiguous: bool = False
    alternative_matches: list["RuleMatch"] = field(default_factory=list)


@dataclass
class ConfidenceSignals:
    """
    Individual confidence signals used in weighted evaluation.

    Attributes:
        rule_type_score: Score based on rule type (vendor_only > vendor_item)
        similarity_score: Embedding similarity score (0.0-1.0)
        uniqueness_score: How unique/unambiguous the match is (0.0-1.0)
        historical_score: Historical hit rate for this rule (0.0-1.0)
        extraction_score: OCR/extraction quality score (0.0-1.0)
    """

    rule_type_score: float = 0.0
    similarity_score: float = 0.0
    uniqueness_score: float = 0.0
    historical_score: float = 0.0
    extraction_score: float = 0.0


@dataclass
class HardGate:
    """
    Hard gate that triggers HITL regardless of confidence score.

    Attributes:
        gate_type: Type of gate (new_vendor, high_amount, critical_account)
        triggered: Whether this gate was triggered
        reason: Human-readable explanation
        threshold_value: The threshold that was exceeded (if applicable)
        actual_value: The actual value that triggered the gate (if applicable)
    """

    gate_type: str
    triggered: bool
    reason: str
    threshold_value: Optional[str] = None
    actual_value: Optional[str] = None


@dataclass
class ConfidenceResult:
    """
    Result of confidence evaluation for a booking proposal.

    Combines weighted signals with hard gate checks to determine
    whether automatic booking is allowed or HITL review is required.

    Attributes:
        overall_confidence: Weighted confidence score (0.0-1.0)
        signals: Individual confidence signals with their scores
        recommendation: Whether to auto-book or require HITL review
        hard_gates_triggered: List of hard gates that were triggered
        explanation: Human-readable explanation of the confidence result
        auto_book_threshold: The threshold used for auto-booking decision
    """

    overall_confidence: float
    signals: ConfidenceSignals
    recommendation: ConfidenceRecommendation
    hard_gates_triggered: list[HardGate] = field(default_factory=list)
    explanation: Optional[str] = None
    auto_book_threshold: float = 0.95


class WorkflowStateType(str, Enum):
    """Possible states in the invoice processing workflow."""

    INGESTION = "ingestion"  # Extracting and validating invoice data
    VALIDATION_PENDING = "validation_pending"  # Waiting for HITL to fix validation errors
    RULE_MATCHING = "rule_matching"  # Matching against semantic rules
    RAG_FALLBACK = "rag_fallback"  # No rule match, using RAG for suggestion
    CONFIDENCE_CHECK = "confidence_check"  # Evaluating confidence
    REVIEW_PENDING = "review_pending"  # Waiting for HITL review
    RULE_LEARNING = "rule_learning"  # Creating/updating rules from decision
    FINALIZATION = "finalization"  # Saving booking and audit trail
    COMPLETED = "completed"  # Workflow complete
    ERROR = "error"  # Error state


@dataclass
class WorkflowState:
    """
    Current state of invoice processing workflow.

    Tracks the workflow state and relevant context for a single invoice.
    Note: In MVP, the agent works sequentially - this model supports
    future state machine implementation (Phase 2).

    Attributes:
        state: Current workflow state
        invoice_id: ID of the invoice being processed
        session_id: Session ID for the processing run
        confidence: Current confidence score (if evaluated)
        hitl_required: Whether HITL review is required
        hitl_reason: Reason for HITL requirement
        rule_match: The rule match result (if matched)
        booking_proposal: The proposed booking (if generated)
        error_message: Error message if in error state
        created_at: ISO timestamp of state creation
        updated_at: ISO timestamp of last state update
    """

    state: WorkflowStateType
    invoice_id: str
    session_id: str
    confidence: Optional[float] = None
    hitl_required: bool = False
    hitl_reason: Optional[str] = None
    rule_match: Optional[RuleMatch] = None
    booking_proposal: Optional[BookingProposal] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
