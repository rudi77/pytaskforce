"""
Accounting Domain Errors

This module defines domain-specific exceptions for accounting operations.
These exceptions are used to signal specific error conditions that can
be caught and handled appropriately by the application layer.
"""


class AccountingError(Exception):
    """
    Base exception for all accounting-related errors.

    All accounting exceptions inherit from this class, allowing
    for broad exception catching when needed.
    """

    def __init__(self, message: str, details: dict | None = None):
        """
        Initialize AccountingError.

        Args:
            message: Human-readable error message
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvoiceParseError(AccountingError):
    """
    Exception raised when invoice parsing fails.

    This can occur when:
    - PDF/image cannot be read
    - OCR/extraction fails
    - Required fields cannot be identified
    - Data format is invalid
    """

    def __init__(
        self,
        message: str,
        source_file: str | None = None,
        extraction_step: str | None = None,
        details: dict | None = None,
    ):
        """
        Initialize InvoiceParseError.

        Args:
            message: Human-readable error message
            source_file: Path to the file that failed to parse
            extraction_step: Step in extraction pipeline that failed
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.source_file = source_file
        self.extraction_step = extraction_step


class ComplianceValidationError(AccountingError):
    """
    Exception raised when compliance validation fails critically.

    This is raised for severe compliance issues that prevent
    further processing, not for warnings or recoverable issues.
    """

    def __init__(
        self,
        message: str,
        missing_fields: list[str] | None = None,
        legal_reference: str | None = None,
        details: dict | None = None,
    ):
        """
        Initialize ComplianceValidationError.

        Args:
            message: Human-readable error message
            missing_fields: List of missing mandatory field names
            legal_reference: Relevant legal reference (e.g., "§14 Abs. 4 UStG")
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.missing_fields = missing_fields or []
        self.legal_reference = legal_reference


class RuleEngineError(AccountingError):
    """
    Exception raised when rule engine encounters an error.

    This can occur when:
    - Rule YAML files are malformed
    - Rule conditions cannot be evaluated
    - No matching rule is found
    """

    def __init__(
        self,
        message: str,
        rule_file: str | None = None,
        rule_name: str | None = None,
        details: dict | None = None,
    ):
        """
        Initialize RuleEngineError.

        Args:
            message: Human-readable error message
            rule_file: Path to the rule file that caused the error
            rule_name: Name of the specific rule that failed
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.rule_file = rule_file
        self.rule_name = rule_name


class TaxCalculationError(AccountingError):
    """
    Exception raised when tax calculation fails.

    This can occur when:
    - Invalid tax rate is provided
    - Amount is invalid
    - Calculation type is unknown
    """

    def __init__(
        self,
        message: str,
        calculation_type: str | None = None,
        amount: str | None = None,
        details: dict | None = None,
    ):
        """
        Initialize TaxCalculationError.

        Args:
            message: Human-readable error message
            calculation_type: Type of calculation that failed
            amount: Amount that caused the error
            details: Optional dictionary with additional error details
        """
        super().__init__(message, details)
        self.calculation_type = calculation_type
        self.amount = amount
