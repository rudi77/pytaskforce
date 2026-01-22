"""Agent catalog and versioning for enterprise deployment.

This module provides a catalog system for managing agent definitions
with version control and deployment lifecycle management.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timezone
from enum import Enum
import uuid
import hashlib
import json


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class VersionStatus(Enum):
    """Version lifecycle status."""

    DRAFT = "draft"  # Being developed
    PENDING_APPROVAL = "pending_approval"  # Awaiting approval
    APPROVED = "approved"  # Approved for deployment
    PUBLISHED = "published"  # Available for use
    DEPRECATED = "deprecated"  # Marked for removal
    ARCHIVED = "archived"  # No longer active


@dataclass
class AgentVersion:
    """A version of an agent definition.

    Attributes:
        version_id: Unique version identifier
        version_number: Semantic version (e.g., "1.0.0")
        agent_id: Parent agent ID
        status: Version status
        definition: Agent definition/configuration
        config_hash: Hash of configuration for change detection
        created_at: When version was created
        created_by: User who created the version
        approved_at: When version was approved
        approved_by: User who approved
        published_at: When version was published
        changelog: Version changelog
        metadata: Additional metadata
    """

    version_id: str
    version_number: str
    agent_id: str
    status: VersionStatus
    definition: Dict[str, Any]
    config_hash: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    created_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    published_at: Optional[datetime] = None
    changelog: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.config_hash:
            self.config_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute hash of the definition."""
        content = json.dumps(self.definition, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def is_editable(self) -> bool:
        """Check if this version can be edited.

        Returns:
            True if version is in draft status
        """
        return self.status == VersionStatus.DRAFT

    def is_deployable(self) -> bool:
        """Check if this version can be deployed.

        Returns:
            True if version is approved or published
        """
        return self.status in (VersionStatus.APPROVED, VersionStatus.PUBLISHED)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version_id": self.version_id,
            "version_number": self.version_number,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "definition": self.definition,
            "config_hash": self.config_hash,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "changelog": self.changelog,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentVersion":
        """Create from dictionary."""
        return cls(
            version_id=data["version_id"],
            version_number=data["version_number"],
            agent_id=data["agent_id"],
            status=VersionStatus(data["status"]),
            definition=data["definition"],
            config_hash=data.get("config_hash", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
            approved_at=datetime.fromisoformat(data["approved_at"]) if data.get("approved_at") else None,
            approved_by=data.get("approved_by"),
            published_at=datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None,
            changelog=data.get("changelog", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentCatalogEntry:
    """An entry in the agent catalog.

    Attributes:
        agent_id: Unique agent identifier
        tenant_id: Tenant that owns this agent
        name: Agent display name
        description: Agent description
        category: Agent category
        tags: Searchable tags
        owner_id: User who owns the agent
        versions: List of versions
        current_version: Currently published version
        created_at: When agent was created
        updated_at: When agent was last updated
        metadata: Additional metadata
    """

    agent_id: str
    tenant_id: str
    name: str
    description: str = ""
    category: str = "general"
    tags: Set[str] = field(default_factory=set)
    owner_id: Optional[str] = None
    versions: List[AgentVersion] = field(default_factory=list)
    current_version: Optional[str] = None  # version_id
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_version(self, version: AgentVersion) -> None:
        """Add a new version to the agent.

        Args:
            version: Version to add
        """
        self.versions.append(version)
        self.updated_at = _utcnow()

    def get_version(self, version_id: str) -> Optional[AgentVersion]:
        """Get a specific version.

        Args:
            version_id: Version ID to find

        Returns:
            AgentVersion if found
        """
        for v in self.versions:
            if v.version_id == version_id:
                return v
        return None

    def get_version_by_number(self, version_number: str) -> Optional[AgentVersion]:
        """Get version by version number.

        Args:
            version_number: Semantic version string

        Returns:
            AgentVersion if found
        """
        for v in self.versions:
            if v.version_number == version_number:
                return v
        return None

    def get_current_version(self) -> Optional[AgentVersion]:
        """Get the current published version.

        Returns:
            Current AgentVersion if one is published
        """
        if self.current_version:
            return self.get_version(self.current_version)
        # Fallback to latest published
        for v in reversed(self.versions):
            if v.status == VersionStatus.PUBLISHED:
                return v
        return None

    def get_latest_version(self) -> Optional[AgentVersion]:
        """Get the latest version regardless of status.

        Returns:
            Latest AgentVersion
        """
        if self.versions:
            return self.versions[-1]
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "owner_id": self.owner_id,
            "versions": [v.to_dict() for v in self.versions],
            "current_version": self.current_version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCatalogEntry":
        """Create from dictionary."""
        entry = cls(
            agent_id=data["agent_id"],
            tenant_id=data["tenant_id"],
            name=data["name"],
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tags=set(data.get("tags", [])),
            owner_id=data.get("owner_id"),
            current_version=data.get("current_version"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )
        entry.versions = [AgentVersion.from_dict(v) for v in data.get("versions", [])]
        return entry


class AgentCatalog:
    """Manages the agent catalog with versioning.

    This class provides catalog management for agents with
    version control and lifecycle management.
    """

    def __init__(self):
        """Initialize the agent catalog."""
        self._entries: Dict[str, AgentCatalogEntry] = {}
        self._by_tenant: Dict[str, List[str]] = {}  # tenant_id -> agent_ids

    def create_agent(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        category: str = "general",
        tags: Optional[Set[str]] = None,
        owner_id: Optional[str] = None,
        initial_definition: Optional[Dict[str, Any]] = None,
    ) -> AgentCatalogEntry:
        """Create a new agent in the catalog.

        Args:
            tenant_id: Tenant ID
            name: Agent name
            description: Agent description
            category: Agent category
            tags: Optional tags
            owner_id: Optional owner user ID
            initial_definition: Optional initial version definition

        Returns:
            Created agent catalog entry
        """
        agent_id = str(uuid.uuid4())

        entry = AgentCatalogEntry(
            agent_id=agent_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            category=category,
            tags=tags or set(),
            owner_id=owner_id,
        )

        # Create initial version if definition provided
        if initial_definition:
            version = AgentVersion(
                version_id=str(uuid.uuid4()),
                version_number="0.1.0",
                agent_id=agent_id,
                status=VersionStatus.DRAFT,
                definition=initial_definition,
                created_by=owner_id,
            )
            entry.add_version(version)

        self._entries[agent_id] = entry

        if tenant_id not in self._by_tenant:
            self._by_tenant[tenant_id] = []
        self._by_tenant[tenant_id].append(agent_id)

        return entry

    def get_agent(self, agent_id: str) -> Optional[AgentCatalogEntry]:
        """Get an agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent entry if found
        """
        return self._entries.get(agent_id)

    def list_agents(
        self,
        tenant_id: str,
        category: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        status: Optional[VersionStatus] = None,
    ) -> List[AgentCatalogEntry]:
        """List agents for a tenant.

        Args:
            tenant_id: Tenant ID
            category: Optional category filter
            tags: Optional tags filter (any match)
            status: Optional status filter (for current version)

        Returns:
            List of matching agents
        """
        agent_ids = self._by_tenant.get(tenant_id, [])
        agents = [self._entries[aid] for aid in agent_ids if aid in self._entries]

        if category:
            agents = [a for a in agents if a.category == category]

        if tags:
            agents = [a for a in agents if a.tags & tags]

        if status:
            agents = [
                a for a in agents
                if a.get_current_version() and a.get_current_version().status == status
            ]

        return agents

    def create_version(
        self,
        agent_id: str,
        version_number: str,
        definition: Dict[str, Any],
        created_by: Optional[str] = None,
        changelog: str = "",
    ) -> Optional[AgentVersion]:
        """Create a new version for an agent.

        Args:
            agent_id: Agent ID
            version_number: Semantic version number
            definition: Agent definition
            created_by: User creating the version
            changelog: Version changelog

        Returns:
            Created version, or None if agent not found
        """
        entry = self._entries.get(agent_id)
        if not entry:
            return None

        version = AgentVersion(
            version_id=str(uuid.uuid4()),
            version_number=version_number,
            agent_id=agent_id,
            status=VersionStatus.DRAFT,
            definition=definition,
            created_by=created_by,
            changelog=changelog,
        )

        entry.add_version(version)
        return version

    def submit_for_approval(
        self,
        agent_id: str,
        version_id: str,
    ) -> bool:
        """Submit a version for approval.

        Args:
            agent_id: Agent ID
            version_id: Version ID

        Returns:
            True if submitted successfully
        """
        entry = self._entries.get(agent_id)
        if not entry:
            return False

        version = entry.get_version(version_id)
        if not version or version.status != VersionStatus.DRAFT:
            return False

        version.status = VersionStatus.PENDING_APPROVAL
        entry.updated_at = _utcnow()
        return True

    def approve_version(
        self,
        agent_id: str,
        version_id: str,
        approved_by: str,
    ) -> bool:
        """Approve a version.

        Args:
            agent_id: Agent ID
            version_id: Version ID
            approved_by: User approving

        Returns:
            True if approved successfully
        """
        entry = self._entries.get(agent_id)
        if not entry:
            return False

        version = entry.get_version(version_id)
        if not version or version.status != VersionStatus.PENDING_APPROVAL:
            return False

        version.status = VersionStatus.APPROVED
        version.approved_at = _utcnow()
        version.approved_by = approved_by
        entry.updated_at = _utcnow()
        return True

    def reject_version(
        self,
        agent_id: str,
        version_id: str,
        reason: str = "",
    ) -> bool:
        """Reject a version and return to draft.

        Args:
            agent_id: Agent ID
            version_id: Version ID
            reason: Rejection reason

        Returns:
            True if rejected successfully
        """
        entry = self._entries.get(agent_id)
        if not entry:
            return False

        version = entry.get_version(version_id)
        if not version or version.status != VersionStatus.PENDING_APPROVAL:
            return False

        version.status = VersionStatus.DRAFT
        version.metadata["rejection_reason"] = reason
        version.metadata["rejected_at"] = _utcnow().isoformat()
        entry.updated_at = _utcnow()
        return True

    def publish_version(
        self,
        agent_id: str,
        version_id: str,
    ) -> bool:
        """Publish a version, making it current.

        Args:
            agent_id: Agent ID
            version_id: Version ID

        Returns:
            True if published successfully
        """
        entry = self._entries.get(agent_id)
        if not entry:
            return False

        version = entry.get_version(version_id)
        if not version or version.status != VersionStatus.APPROVED:
            return False

        # Deprecate current version if exists
        current = entry.get_current_version()
        if current and current.version_id != version_id:
            current.status = VersionStatus.DEPRECATED

        version.status = VersionStatus.PUBLISHED
        version.published_at = _utcnow()
        entry.current_version = version_id
        entry.updated_at = _utcnow()
        return True

    def deprecate_version(
        self,
        agent_id: str,
        version_id: str,
    ) -> bool:
        """Deprecate a published version.

        Args:
            agent_id: Agent ID
            version_id: Version ID

        Returns:
            True if deprecated successfully
        """
        entry = self._entries.get(agent_id)
        if not entry:
            return False

        version = entry.get_version(version_id)
        if not version or version.status != VersionStatus.PUBLISHED:
            return False

        version.status = VersionStatus.DEPRECATED
        if entry.current_version == version_id:
            entry.current_version = None
        entry.updated_at = _utcnow()
        return True

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent from the catalog.

        Args:
            agent_id: Agent ID

        Returns:
            True if deleted successfully
        """
        entry = self._entries.get(agent_id)
        if not entry:
            return False

        # Remove from tenant index
        if entry.tenant_id in self._by_tenant:
            if agent_id in self._by_tenant[entry.tenant_id]:
                self._by_tenant[entry.tenant_id].remove(agent_id)

        del self._entries[agent_id]
        return True

    def search_agents(
        self,
        tenant_id: str,
        query: str,
        limit: int = 50,
    ) -> List[AgentCatalogEntry]:
        """Search agents by name, description, or tags.

        Args:
            tenant_id: Tenant ID
            query: Search query
            limit: Maximum results

        Returns:
            List of matching agents
        """
        agents = self.list_agents(tenant_id)
        query_lower = query.lower()

        results = []
        for agent in agents:
            # Check name
            if query_lower in agent.name.lower():
                results.append(agent)
                continue
            # Check description
            if query_lower in agent.description.lower():
                results.append(agent)
                continue
            # Check tags
            if any(query_lower in tag.lower() for tag in agent.tags):
                results.append(agent)

        return results[:limit]
