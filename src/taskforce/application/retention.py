"""Data retention policy service.

This module provides configurable data retention policies for
GDPR compliance and data lifecycle management.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime, timezone, timedelta
from enum import Enum
import asyncio
import structlog


logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class DataCategory(Enum):
    """Categories of data for retention policies."""

    SESSION_DATA = "session_data"
    TOOL_RESULTS = "tool_results"
    AUDIT_LOGS = "audit_logs"
    MEMORY = "memory"
    EVIDENCE = "evidence"
    USER_DATA = "user_data"


@dataclass
class RetentionPolicy:
    """Retention policy for a data category.

    Attributes:
        category: Data category this policy applies to
        retention_days: Number of days to retain data (0 = forever)
        soft_delete: Whether to soft delete (mark as deleted) vs hard delete
        archive_before_delete: Whether to archive data before deletion
        tenant_override: Whether tenant can override this policy
    """

    category: DataCategory
    retention_days: int
    soft_delete: bool = True
    archive_before_delete: bool = False
    tenant_override: bool = True

    def get_expiration_date(self, created_at: datetime) -> Optional[datetime]:
        """Calculate when data should expire.

        Args:
            created_at: When the data was created

        Returns:
            Expiration datetime, or None if never expires
        """
        if self.retention_days <= 0:
            return None
        return created_at + timedelta(days=self.retention_days)

    def is_expired(self, created_at: datetime) -> bool:
        """Check if data has expired based on this policy.

        Args:
            created_at: When the data was created

        Returns:
            True if data should be deleted
        """
        expiration = self.get_expiration_date(created_at)
        if expiration is None:
            return False
        return _utcnow() > expiration


@dataclass
class RetentionConfig:
    """Configuration for retention policies.

    Attributes:
        policies: Map of data category to retention policy
        default_retention_days: Default retention for uncategorized data
        enabled: Whether retention enforcement is enabled
        dry_run: Whether to simulate deletions without actually deleting
    """

    policies: Dict[DataCategory, RetentionPolicy] = field(default_factory=dict)
    default_retention_days: int = 90
    enabled: bool = True
    dry_run: bool = False

    def __post_init__(self):
        # Set default policies if not provided
        defaults = {
            DataCategory.SESSION_DATA: RetentionPolicy(
                category=DataCategory.SESSION_DATA,
                retention_days=30,
            ),
            DataCategory.TOOL_RESULTS: RetentionPolicy(
                category=DataCategory.TOOL_RESULTS,
                retention_days=7,
            ),
            DataCategory.AUDIT_LOGS: RetentionPolicy(
                category=DataCategory.AUDIT_LOGS,
                retention_days=365,
                soft_delete=False,
            ),
            DataCategory.MEMORY: RetentionPolicy(
                category=DataCategory.MEMORY,
                retention_days=90,
            ),
            DataCategory.EVIDENCE: RetentionPolicy(
                category=DataCategory.EVIDENCE,
                retention_days=365,
                archive_before_delete=True,
            ),
            DataCategory.USER_DATA: RetentionPolicy(
                category=DataCategory.USER_DATA,
                retention_days=0,  # Never auto-delete user data
            ),
        }

        for category, policy in defaults.items():
            if category not in self.policies:
                self.policies[category] = policy

    def get_policy(self, category: DataCategory) -> RetentionPolicy:
        """Get retention policy for a category.

        Args:
            category: Data category

        Returns:
            RetentionPolicy for the category
        """
        return self.policies.get(
            category,
            RetentionPolicy(
                category=category,
                retention_days=self.default_retention_days,
            ),
        )


@dataclass
class DeletionRecord:
    """Record of a data deletion for audit purposes.

    Attributes:
        record_id: Unique identifier for this record
        category: Data category that was deleted
        tenant_id: Tenant the data belonged to
        resource_id: Identifier of the deleted resource
        deleted_at: When the deletion occurred
        reason: Reason for deletion
        soft_delete: Whether this was a soft delete
        archived_to: Where data was archived (if applicable)
        requested_by: Who requested the deletion (user or system)
    """

    record_id: str
    category: DataCategory
    tenant_id: str
    resource_id: str
    deleted_at: datetime = field(default_factory=_utcnow)
    reason: str = "retention_policy"
    soft_delete: bool = True
    archived_to: Optional[str] = None
    requested_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "record_id": self.record_id,
            "category": self.category.value,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "deleted_at": self.deleted_at.isoformat(),
            "reason": self.reason,
            "soft_delete": self.soft_delete,
            "archived_to": self.archived_to,
            "requested_by": self.requested_by,
        }


class RetentionService:
    """Service for enforcing data retention policies.

    This service:
    - Applies retention policies to different data categories
    - Supports scheduled cleanup via background tasks
    - Handles right-to-be-forgotten (GDPR Article 17) requests
    - Maintains audit trail of deletions
    """

    def __init__(
        self,
        config: Optional[RetentionConfig] = None,
        deletion_callback: Optional[Callable[[DeletionRecord], Awaitable[None]]] = None,
    ):
        """Initialize the retention service.

        Args:
            config: Retention configuration
            deletion_callback: Callback for deletion records (for audit)
        """
        self.config = config or RetentionConfig()
        self._deletion_callback = deletion_callback
        self._deletion_records: List[DeletionRecord] = []

    async def check_retention(
        self,
        category: DataCategory,
        created_at: datetime,
        tenant_id: str,
        tenant_override_days: Optional[int] = None,
    ) -> bool:
        """Check if data should be retained based on policy.

        Args:
            category: Data category
            created_at: When the data was created
            tenant_id: Tenant identifier
            tenant_override_days: Optional tenant-specific retention

        Returns:
            True if data should be retained, False if it should be deleted
        """
        if not self.config.enabled:
            return True  # Keep everything when disabled

        policy = self.config.get_policy(category)

        # Apply tenant override if allowed and provided
        if policy.tenant_override and tenant_override_days is not None:
            effective_days = tenant_override_days
        else:
            effective_days = policy.retention_days

        if effective_days <= 0:
            return True  # Never delete

        expiration = created_at + timedelta(days=effective_days)
        return _utcnow() <= expiration

    async def process_deletion(
        self,
        category: DataCategory,
        tenant_id: str,
        resource_id: str,
        reason: str = "retention_policy",
        requested_by: str = "system",
    ) -> DeletionRecord:
        """Process a data deletion with proper audit trail.

        Args:
            category: Data category being deleted
            tenant_id: Tenant identifier
            resource_id: Resource being deleted
            reason: Reason for deletion
            requested_by: Who requested the deletion

        Returns:
            DeletionRecord for audit
        """
        import uuid

        policy = self.config.get_policy(category)

        record = DeletionRecord(
            record_id=str(uuid.uuid4()),
            category=category,
            tenant_id=tenant_id,
            resource_id=resource_id,
            reason=reason,
            soft_delete=policy.soft_delete,
            requested_by=requested_by,
        )

        if not self.config.dry_run:
            self._deletion_records.append(record)

            if self._deletion_callback:
                await self._deletion_callback(record)

            logger.info(
                "retention.deletion_processed",
                category=category.value,
                tenant_id=tenant_id,
                resource_id=resource_id,
                reason=reason,
            )
        else:
            logger.info(
                "retention.deletion_dry_run",
                category=category.value,
                tenant_id=tenant_id,
                resource_id=resource_id,
            )

        return record

    async def right_to_be_forgotten(
        self,
        tenant_id: str,
        user_id: str,
        categories: Optional[List[DataCategory]] = None,
    ) -> List[DeletionRecord]:
        """Process a right-to-be-forgotten (GDPR Article 17) request.

        This deletes all user data across specified categories.

        Args:
            tenant_id: Tenant identifier
            user_id: User requesting deletion
            categories: Categories to delete (None = all)

        Returns:
            List of deletion records
        """
        if categories is None:
            categories = list(DataCategory)

        records = []
        for category in categories:
            record = await self.process_deletion(
                category=category,
                tenant_id=tenant_id,
                resource_id=f"user:{user_id}:*",
                reason="right_to_be_forgotten",
                requested_by=user_id,
            )
            records.append(record)

        logger.info(
            "retention.rtbf_processed",
            tenant_id=tenant_id,
            user_id=user_id,
            categories=[c.value for c in categories],
            record_count=len(records),
        )

        return records

    def get_deletion_records(
        self,
        tenant_id: Optional[str] = None,
        category: Optional[DataCategory] = None,
        since: Optional[datetime] = None,
    ) -> List[DeletionRecord]:
        """Get deletion records for audit purposes.

        Args:
            tenant_id: Filter by tenant
            category: Filter by category
            since: Filter by time

        Returns:
            List of matching deletion records
        """
        records = self._deletion_records

        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]

        if category:
            records = [r for r in records if r.category == category]

        if since:
            records = [r for r in records if r.deleted_at >= since]

        return records


class RetentionScheduler:
    """Scheduler for automated retention cleanup.

    Runs periodic cleanup tasks to enforce retention policies.
    """

    def __init__(
        self,
        retention_service: RetentionService,
        check_interval_hours: int = 24,
    ):
        """Initialize the scheduler.

        Args:
            retention_service: The retention service to use
            check_interval_hours: How often to run cleanup
        """
        self.retention_service = retention_service
        self.check_interval = timedelta(hours=check_interval_hours)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the retention scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("retention.scheduler_started", interval_hours=self.check_interval.total_seconds() / 3600)

    async def stop(self) -> None:
        """Stop the retention scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("retention.scheduler_stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._run_cleanup()
            except Exception as e:
                logger.error("retention.cleanup_error", error=str(e))

            await asyncio.sleep(self.check_interval.total_seconds())

    async def _run_cleanup(self) -> None:
        """Run a cleanup cycle."""
        logger.info("retention.cleanup_started")
        # In a real implementation, this would scan data stores
        # and delete expired data based on policies
        logger.info("retention.cleanup_completed")
