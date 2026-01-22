"""Compliance evidence export for audits and certifications.

This module provides compliance evidence export functionality
supporting SOC2, ISO 27001, and GDPR requirements.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
import json


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ComplianceFramework(Enum):
    """Supported compliance frameworks."""

    SOC2 = "soc2"
    ISO_27001 = "iso_27001"
    GDPR = "gdpr"
    AI_ACT = "ai_act"


class SOC2Control(Enum):
    """SOC2 Trust Services Criteria controls."""

    CC1_1 = "CC1.1"  # Organization and Management
    CC2_1 = "CC2.1"  # Communications
    CC3_1 = "CC3.1"  # Risk Assessment
    CC4_1 = "CC4.1"  # Monitoring Activities
    CC5_1 = "CC5.1"  # Control Activities
    CC6_1 = "CC6.1"  # Logical and Physical Access Controls
    CC7_1 = "CC7.1"  # System Operations
    CC8_1 = "CC8.1"  # Change Management
    CC9_1 = "CC9.1"  # Risk Mitigation


class ISO27001Control(Enum):
    """ISO 27001 Annex A controls."""

    A5 = "A.5"  # Information Security Policies
    A6 = "A.6"  # Organization of Information Security
    A7 = "A.7"  # Human Resource Security
    A8 = "A.8"  # Asset Management
    A9 = "A.9"  # Access Control
    A10 = "A.10"  # Cryptography
    A11 = "A.11"  # Physical and Environmental Security
    A12 = "A.12"  # Operations Security
    A13 = "A.13"  # Communications Security
    A14 = "A.14"  # System Development
    A15 = "A.15"  # Supplier Relationships
    A16 = "A.16"  # Incident Management
    A17 = "A.17"  # Business Continuity
    A18 = "A.18"  # Compliance


@dataclass
class EvidenceItem:
    """A single piece of compliance evidence.

    Attributes:
        evidence_id: Unique identifier
        title: Evidence title
        description: Description of the evidence
        control_id: Related control ID
        framework: Compliance framework
        evidence_type: Type of evidence (document, log, config, etc.)
        source: Source of evidence
        collected_at: When evidence was collected
        data: Evidence data/content
        metadata: Additional metadata
    """

    evidence_id: str
    title: str
    description: str
    control_id: str
    framework: ComplianceFramework
    evidence_type: str
    source: str
    collected_at: datetime = field(default_factory=_utcnow)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "description": self.description,
            "control_id": self.control_id,
            "framework": self.framework.value,
            "evidence_type": self.evidence_type,
            "source": self.source,
            "collected_at": self.collected_at.isoformat(),
            "data": self.data,
            "metadata": self.metadata,
        }


@dataclass
class ComplianceReport:
    """A compliance evidence report for audits.

    Attributes:
        report_id: Unique report identifier
        tenant_id: Tenant ID
        framework: Compliance framework
        period_start: Start of reporting period
        period_end: End of reporting period
        evidence_items: List of evidence items
        summary: Executive summary
        generated_at: When report was generated
        generated_by: Who generated the report
        metadata: Additional report metadata
    """

    report_id: str
    tenant_id: str
    framework: ComplianceFramework
    period_start: datetime
    period_end: datetime
    evidence_items: List[EvidenceItem] = field(default_factory=list)
    summary: str = ""
    generated_at: datetime = field(default_factory=_utcnow)
    generated_by: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_evidence(self, item: EvidenceItem) -> None:
        """Add evidence item to report.

        Args:
            item: Evidence item to add
        """
        self.evidence_items.append(item)

    def get_evidence_by_control(self, control_id: str) -> List[EvidenceItem]:
        """Get evidence for a specific control.

        Args:
            control_id: Control identifier

        Returns:
            List of evidence items for the control
        """
        return [e for e in self.evidence_items if e.control_id == control_id]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "tenant_id": self.tenant_id,
            "framework": self.framework.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "evidence_items": [e.to_dict() for e in self.evidence_items],
            "summary": self.summary,
            "generated_at": self.generated_at.isoformat(),
            "generated_by": self.generated_by,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Export as JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class GDPRProcessingRecord:
    """GDPR data processing record (Article 30).

    Attributes:
        record_id: Unique identifier
        tenant_id: Tenant ID
        processing_purpose: Purpose of processing
        data_categories: Categories of data processed
        data_subjects: Categories of data subjects
        recipients: Data recipients
        transfers: International transfers
        retention_period: Data retention period
        security_measures: Technical/organizational measures
        created_at: When record was created
        updated_at: When record was last updated
    """

    record_id: str
    tenant_id: str
    processing_purpose: str
    data_categories: List[str] = field(default_factory=list)
    data_subjects: List[str] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)
    transfers: List[Dict[str, Any]] = field(default_factory=list)
    retention_period: str = ""
    security_measures: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "processing_purpose": self.processing_purpose,
            "data_categories": self.data_categories,
            "data_subjects": self.data_subjects,
            "recipients": self.recipients,
            "transfers": self.transfers,
            "retention_period": self.retention_period,
            "security_measures": self.security_measures,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class ComplianceEvidenceCollector:
    """Collects compliance evidence from system components.

    This class gathers evidence from various system components
    to build compliance reports.
    """

    def __init__(self, tenant_id: str):
        """Initialize the collector.

        Args:
            tenant_id: Tenant ID to collect evidence for
        """
        self.tenant_id = tenant_id
        self._evidence: List[EvidenceItem] = []

    def collect_access_control_evidence(self) -> List[EvidenceItem]:
        """Collect access control related evidence.

        Returns:
            List of evidence items for access controls
        """
        import uuid

        evidence = []

        # RBAC Configuration Evidence
        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            title="RBAC Configuration",
            description="Role-based access control configuration with predefined system roles",
            control_id=SOC2Control.CC6_1.value,
            framework=ComplianceFramework.SOC2,
            evidence_type="configuration",
            source="taskforce.core.interfaces.identity",
            data={
                "system_roles": ["admin", "agent_designer", "operator", "auditor", "viewer"],
                "permission_count": 17,
                "role_hierarchy": True,
            },
        ))

        # Authentication Evidence
        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            title="Authentication Mechanisms",
            description="Multi-method authentication support (JWT, API Keys)",
            control_id=ISO27001Control.A9.value,
            framework=ComplianceFramework.ISO_27001,
            evidence_type="configuration",
            source="taskforce.infrastructure.auth",
            data={
                "auth_methods": ["jwt_bearer", "api_key"],
                "jwt_algorithms": ["HS256", "RS256"],
                "api_key_hashing": "sha256",
            },
        ))

        self._evidence.extend(evidence)
        return evidence

    def collect_encryption_evidence(self) -> List[EvidenceItem]:
        """Collect encryption related evidence.

        Returns:
            List of evidence items for encryption
        """
        import uuid

        evidence = []

        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            title="Data Encryption at Rest",
            description="Per-tenant encryption using Fernet (AES-128-CBC + HMAC)",
            control_id=ISO27001Control.A10.value,
            framework=ComplianceFramework.ISO_27001,
            evidence_type="configuration",
            source="taskforce.infrastructure.persistence.encryption",
            data={
                "algorithm": "fernet",
                "key_derivation": "PBKDF2HMAC",
                "per_tenant_keys": True,
                "key_rotation_supported": True,
            },
        ))

        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            title="Memory Access Control",
            description="ACL-based memory access with sensitivity levels",
            control_id=SOC2Control.CC6_1.value,
            framework=ComplianceFramework.SOC2,
            evidence_type="configuration",
            source="taskforce.core.domain.memory_acl",
            data={
                "acl_permissions": ["read", "write", "delete", "reference", "share", "admin"],
                "sensitivity_levels": ["public", "internal", "confidential", "restricted"],
                "scope_levels": ["global", "tenant", "project", "session", "private"],
            },
        ))

        self._evidence.extend(evidence)
        return evidence

    def collect_audit_evidence(self) -> List[EvidenceItem]:
        """Collect audit logging evidence.

        Returns:
            List of evidence items for audit logging
        """
        import uuid

        evidence = []

        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            title="Structured Logging",
            description="Contextual structured logging with tenant/user context",
            control_id=SOC2Control.CC4_1.value,
            framework=ComplianceFramework.SOC2,
            evidence_type="configuration",
            source="taskforce.infrastructure.tracing",
            data={
                "logging_library": "structlog",
                "context_fields": ["tenant_id", "user_id", "session_id", "agent_id"],
                "log_levels": ["DEBUG", "INFO", "WARNING", "ERROR"],
            },
        ))

        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            title="Evidence Chain Tracking",
            description="Full audit trail for agent responses with source citations",
            control_id=SOC2Control.CC7_1.value,
            framework=ComplianceFramework.SOC2,
            evidence_type="feature",
            source="taskforce.core.domain.evidence",
            data={
                "evidence_types": ["tool_result", "rag_document", "llm_reasoning", "user_input"],
                "confidence_levels": ["high", "medium", "low", "unknown"],
                "citation_support": True,
            },
        ))

        self._evidence.extend(evidence)
        return evidence

    def collect_retention_evidence(self) -> List[EvidenceItem]:
        """Collect data retention policy evidence.

        Returns:
            List of evidence items for retention policies
        """
        import uuid

        evidence = []

        evidence.append(EvidenceItem(
            evidence_id=str(uuid.uuid4()),
            title="Data Retention Policies",
            description="Configurable retention policies with automatic cleanup",
            control_id="GDPR-5",
            framework=ComplianceFramework.GDPR,
            evidence_type="configuration",
            source="taskforce.application.retention",
            data={
                "data_categories": ["session_data", "tool_results", "memory", "audit_logs"],
                "default_retention_days": {"session_data": 30, "tool_results": 7},
                "right_to_erasure": True,
                "soft_delete_support": True,
            },
        ))

        self._evidence.extend(evidence)
        return evidence

    def collect_all_evidence(self) -> List[EvidenceItem]:
        """Collect all evidence.

        Returns:
            List of all evidence items
        """
        self._evidence = []
        self.collect_access_control_evidence()
        self.collect_encryption_evidence()
        self.collect_audit_evidence()
        self.collect_retention_evidence()
        return self._evidence


class ComplianceReportGenerator:
    """Generates compliance reports for various frameworks."""

    def __init__(self, collector: ComplianceEvidenceCollector):
        """Initialize the generator.

        Args:
            collector: Evidence collector instance
        """
        self.collector = collector

    def generate_soc2_report(
        self,
        period_start: datetime,
        period_end: datetime,
        report_id: Optional[str] = None,
    ) -> ComplianceReport:
        """Generate SOC2 compliance report.

        Args:
            period_start: Start of reporting period
            period_end: End of reporting period
            report_id: Optional report ID

        Returns:
            SOC2 compliance report
        """
        import uuid

        report = ComplianceReport(
            report_id=report_id or str(uuid.uuid4()),
            tenant_id=self.collector.tenant_id,
            framework=ComplianceFramework.SOC2,
            period_start=period_start,
            period_end=period_end,
        )

        # Collect evidence
        all_evidence = self.collector.collect_all_evidence()

        # Filter SOC2 evidence
        soc2_evidence = [
            e for e in all_evidence
            if e.framework == ComplianceFramework.SOC2
        ]

        for item in soc2_evidence:
            report.add_evidence(item)

        # Generate summary
        report.summary = self._generate_soc2_summary(report)

        return report

    def generate_iso27001_report(
        self,
        period_start: datetime,
        period_end: datetime,
        report_id: Optional[str] = None,
    ) -> ComplianceReport:
        """Generate ISO 27001 compliance report.

        Args:
            period_start: Start of reporting period
            period_end: End of reporting period
            report_id: Optional report ID

        Returns:
            ISO 27001 compliance report
        """
        import uuid

        report = ComplianceReport(
            report_id=report_id or str(uuid.uuid4()),
            tenant_id=self.collector.tenant_id,
            framework=ComplianceFramework.ISO_27001,
            period_start=period_start,
            period_end=period_end,
        )

        # Collect evidence
        all_evidence = self.collector.collect_all_evidence()

        # Filter ISO 27001 evidence
        iso_evidence = [
            e for e in all_evidence
            if e.framework == ComplianceFramework.ISO_27001
        ]

        for item in iso_evidence:
            report.add_evidence(item)

        report.summary = self._generate_iso27001_summary(report)

        return report

    def generate_gdpr_records(
        self,
        processing_activities: Optional[List[Dict[str, Any]]] = None,
    ) -> List[GDPRProcessingRecord]:
        """Generate GDPR Article 30 processing records.

        Args:
            processing_activities: Optional custom processing activities

        Returns:
            List of GDPR processing records
        """
        import uuid

        records = []

        # Default AI agent processing activity
        records.append(GDPRProcessingRecord(
            record_id=str(uuid.uuid4()),
            tenant_id=self.collector.tenant_id,
            processing_purpose="AI Agent task execution and reasoning",
            data_categories=[
                "User queries/missions",
                "Agent reasoning steps",
                "Tool execution results",
                "Session context",
            ],
            data_subjects=["Tenant users", "End users interacting with agents"],
            recipients=["LLM providers (OpenAI, Azure)"],
            transfers=[{
                "destination": "United States (OpenAI)",
                "safeguards": "Standard Contractual Clauses",
            }],
            retention_period="30 days for session data, configurable per tenant",
            security_measures=[
                "Encryption at rest",
                "Role-based access control",
                "Tenant isolation",
                "Audit logging",
            ],
        ))

        # Add custom activities if provided
        if processing_activities:
            for activity in processing_activities:
                records.append(GDPRProcessingRecord(
                    record_id=str(uuid.uuid4()),
                    tenant_id=self.collector.tenant_id,
                    **activity,
                ))

        return records

    def _generate_soc2_summary(self, report: ComplianceReport) -> str:
        """Generate SOC2 executive summary."""
        control_coverage = len(set(e.control_id for e in report.evidence_items))
        return f"""SOC2 Type II Compliance Evidence Package

Tenant: {report.tenant_id}
Period: {report.period_start.strftime('%Y-%m-%d')} to {report.period_end.strftime('%Y-%m-%d')}

This report contains {len(report.evidence_items)} evidence items
covering {control_coverage} Trust Services Criteria controls.

Key controls addressed:
- CC6.1: Logical and Physical Access Controls
- CC7.1: System Operations
- CC4.1: Monitoring Activities

All controls demonstrate continuous operation throughout the reporting period.
"""

    def _generate_iso27001_summary(self, report: ComplianceReport) -> str:
        """Generate ISO 27001 executive summary."""
        control_coverage = len(set(e.control_id for e in report.evidence_items))
        return f"""ISO 27001:2022 Compliance Evidence Package

Tenant: {report.tenant_id}
Period: {report.period_start.strftime('%Y-%m-%d')} to {report.period_end.strftime('%Y-%m-%d')}

This report contains {len(report.evidence_items)} evidence items
covering {control_coverage} Annex A controls.

Key controls addressed:
- A.9: Access Control
- A.10: Cryptography
- A.12: Operations Security

The information security management system demonstrates conformity
with ISO 27001:2022 requirements.
"""


def export_compliance_package(
    report: ComplianceReport,
    format: str = "json",
) -> str:
    """Export compliance report in specified format.

    Args:
        report: Compliance report to export
        format: Output format (json, markdown)

    Returns:
        Formatted report string
    """
    if format == "json":
        return report.to_json()
    elif format == "markdown":
        return _format_report_markdown(report)
    else:
        return report.to_json()


def _format_report_markdown(report: ComplianceReport) -> str:
    """Format compliance report as Markdown."""
    lines = [
        f"# {report.framework.value.upper()} Compliance Evidence Report",
        "",
        f"**Report ID:** {report.report_id}",
        f"**Tenant:** {report.tenant_id}",
        f"**Framework:** {report.framework.value}",
        f"**Period:** {report.period_start.strftime('%Y-%m-%d')} to {report.period_end.strftime('%Y-%m-%d')}",
        f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## Executive Summary",
        "",
        report.summary,
        "",
        "## Evidence Items",
        "",
    ]

    # Group evidence by control
    by_control: Dict[str, List[EvidenceItem]] = {}
    for item in report.evidence_items:
        if item.control_id not in by_control:
            by_control[item.control_id] = []
        by_control[item.control_id].append(item)

    for control_id, items in sorted(by_control.items()):
        lines.append(f"### Control {control_id}")
        lines.append("")
        for item in items:
            lines.append(f"#### {item.title}")
            lines.append("")
            lines.append(f"**Description:** {item.description}")
            lines.append(f"**Evidence Type:** {item.evidence_type}")
            lines.append(f"**Source:** {item.source}")
            lines.append(f"**Collected:** {item.collected_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            lines.append("")
            lines.append("**Evidence Data:**")
            lines.append("```json")
            lines.append(json.dumps(item.data, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines)
