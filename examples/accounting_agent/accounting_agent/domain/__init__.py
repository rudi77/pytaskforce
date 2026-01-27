"""
Accounting Domain Models

This module provides domain models for German accounting (Buchhaltung) operations.
"""

from accounting_agent.domain.models import (
    # Core invoice models
    BookingProposal,
    ComplianceFields,
    ComplianceResult,
    ComplianceWarning,
    ComplianceError,
    Invoice,
    LineItem,
    # Semantic rules engine models
    AccountingRule,
    RuleType,
    RuleSource,
    RuleMatch,
    MatchType,
    # Confidence evaluation models
    ConfidenceSignals,
    ConfidenceResult,
    ConfidenceRecommendation,
    HardGate,
    # Workflow state models
    WorkflowState,
    WorkflowStateType,
)
from accounting_agent.domain.errors import (
    AccountingError,
    ComplianceValidationError,
    InvoiceParseError,
)
from accounting_agent.domain.protocols import (
    EmbeddingProviderProtocol,
    RuleRepositoryProtocol,
    BookingHistoryProtocol,
    LLMProviderProtocol,
)
from accounting_agent.domain.confidence import ConfidenceCalculator

__all__ = [
    # Errors
    "AccountingError",
    "ComplianceValidationError",
    "InvoiceParseError",
    # Core invoice models
    "BookingProposal",
    "ComplianceError",
    "ComplianceFields",
    "ComplianceResult",
    "ComplianceWarning",
    "Invoice",
    "LineItem",
    # Semantic rules engine models
    "AccountingRule",
    "RuleType",
    "RuleSource",
    "RuleMatch",
    "MatchType",
    # Confidence evaluation models
    "ConfidenceSignals",
    "ConfidenceResult",
    "ConfidenceRecommendation",
    "HardGate",
    # Workflow state models
    "WorkflowState",
    "WorkflowStateType",
    # Protocols
    "EmbeddingProviderProtocol",
    "RuleRepositoryProtocol",
    "BookingHistoryProtocol",
    "LLMProviderProtocol",
    # Confidence calculator
    "ConfidenceCalculator",
]
