"""
Accounting Tools Package

This package provides specialized tools for German accounting operations:

Core Tools:
- DoclingTool: PDF/image to Markdown extraction via Docling CLI
- InvoiceExtractionTool: LLM-based invoice data extraction from markdown
- RuleEngineTool: YAML-based deterministic Kontierung rules (legacy)
- ComplianceCheckerTool: §14 UStG compliance validation
- TaxCalculatorTool: VAT and depreciation calculations
- AuditLogTool: GoBD-compliant audit logging

Semantic Rules Engine (PRD Phase 1):
- SemanticRuleEngineTool: Embedding-based account assignment
- ConfidenceEvaluatorTool: Weighted confidence evaluation
- RAGFallbackTool: LLM-based suggestions when no rules match
- HITLReviewTool: Human-in-the-loop review workflow
- RuleLearningTool: Automatic rule generation

These tools can be integrated with Taskforce agents or used standalone.
"""

from accounting_agent.tools.audit_log_tool import AuditLogTool
from accounting_agent.tools.compliance_checker_tool import ComplianceCheckerTool
from accounting_agent.tools.docling_tool import DoclingTool
from accounting_agent.tools.invoice_extraction_tool import InvoiceExtractionTool
from accounting_agent.tools.rule_engine_tool import RuleEngineTool
from accounting_agent.tools.tax_calculator_tool import TaxCalculatorTool

# Semantic Rules Engine tools (PRD Phase 1)
from accounting_agent.tools.semantic_rule_engine_tool import SemanticRuleEngineTool
from accounting_agent.tools.confidence_evaluator_tool import ConfidenceEvaluatorTool
from accounting_agent.tools.rag_fallback_tool import RAGFallbackTool
from accounting_agent.tools.hitl_review_tool import HITLReviewTool
from accounting_agent.tools.rule_learning_tool import RuleLearningTool

__all__ = [
    # Core tools
    "AuditLogTool",
    "ComplianceCheckerTool",
    "DoclingTool",
    "InvoiceExtractionTool",
    "RuleEngineTool",
    "TaxCalculatorTool",
    # Semantic Rules Engine tools
    "SemanticRuleEngineTool",
    "ConfidenceEvaluatorTool",
    "RAGFallbackTool",
    "HITLReviewTool",
    "RuleLearningTool",
]
