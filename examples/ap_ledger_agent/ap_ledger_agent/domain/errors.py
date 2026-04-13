"""Custom exception hierarchy for the AP Ledger Agent."""


class ApLedgerError(Exception):
    """Base exception for AP Ledger operations."""


class DatabaseError(ApLedgerError):
    """Database operation failed."""


class ValidationError(ApLedgerError):
    """Data validation failed."""


class VendorNotFoundError(ApLedgerError):
    """Vendor could not be resolved."""


class DuplicateInvoiceError(ApLedgerError):
    """Invoice appears to be a duplicate."""


class JournalBalanceError(ApLedgerError):
    """Journal entry is not balanced (Soll != Haben)."""
