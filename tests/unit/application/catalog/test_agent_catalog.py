"""Tests for agent catalog and versioning."""

import pytest
from datetime import datetime, timezone

from taskforce.application.catalog import (
    AgentCatalog,
    AgentCatalogEntry,
    AgentVersion,
    VersionStatus,
)


class TestVersionStatus:
    """Tests for VersionStatus enum."""

    def test_all_statuses_defined(self):
        """Test all expected statuses exist."""
        assert VersionStatus.DRAFT.value == "draft"
        assert VersionStatus.PENDING_APPROVAL.value == "pending_approval"
        assert VersionStatus.APPROVED.value == "approved"
        assert VersionStatus.PUBLISHED.value == "published"
        assert VersionStatus.DEPRECATED.value == "deprecated"
        assert VersionStatus.ARCHIVED.value == "archived"


class TestAgentVersion:
    """Tests for AgentVersion dataclass."""

    def test_create_version(self):
        """Test creating a version."""
        version = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={"name": "test", "tools": []},
            created_by="user1",
        )
        assert version.version_id == "v1"
        assert version.version_number == "1.0.0"
        assert version.agent_id == "agent1"
        assert version.status == VersionStatus.DRAFT
        assert version.config_hash != ""  # Auto-generated

    def test_compute_hash(self):
        """Test that config hash is computed from definition."""
        v1 = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={"name": "test"},
        )
        v2 = AgentVersion(
            version_id="v2",
            version_number="1.0.1",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={"name": "test"},
        )
        v3 = AgentVersion(
            version_id="v3",
            version_number="1.1.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={"name": "different"},
        )
        # Same definition = same hash
        assert v1.config_hash == v2.config_hash
        # Different definition = different hash
        assert v1.config_hash != v3.config_hash

    def test_is_editable(self):
        """Test editable status check."""
        draft = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        published = AgentVersion(
            version_id="v2",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.PUBLISHED,
            definition={},
        )
        assert draft.is_editable() is True
        assert published.is_editable() is False

    def test_is_deployable(self):
        """Test deployable status check."""
        draft = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        approved = AgentVersion(
            version_id="v2",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.APPROVED,
            definition={},
        )
        published = AgentVersion(
            version_id="v3",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.PUBLISHED,
            definition={},
        )
        assert draft.is_deployable() is False
        assert approved.is_deployable() is True
        assert published.is_deployable() is True

    def test_to_dict_and_from_dict(self):
        """Test serialization round trip."""
        original = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.APPROVED,
            definition={"name": "test", "tools": ["tool1"]},
            created_by="user1",
            approved_by="admin1",
            changelog="Initial version",
            metadata={"notes": "test"},
        )
        original.approved_at = datetime.now(timezone.utc)

        data = original.to_dict()
        restored = AgentVersion.from_dict(data)

        assert restored.version_id == original.version_id
        assert restored.version_number == original.version_number
        assert restored.agent_id == original.agent_id
        assert restored.status == original.status
        assert restored.definition == original.definition
        assert restored.created_by == original.created_by
        assert restored.approved_by == original.approved_by
        assert restored.changelog == original.changelog
        assert restored.metadata == original.metadata


class TestAgentCatalogEntry:
    """Tests for AgentCatalogEntry dataclass."""

    def test_create_entry(self):
        """Test creating a catalog entry."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
            description="A test agent",
            category="testing",
            tags={"test", "demo"},
            owner_id="user1",
        )
        assert entry.agent_id == "agent1"
        assert entry.name == "Test Agent"
        assert "test" in entry.tags
        assert entry.versions == []

    def test_add_version(self):
        """Test adding a version to entry."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
        )
        version = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        entry.add_version(version)
        assert len(entry.versions) == 1
        assert entry.versions[0] == version

    def test_get_version(self):
        """Test getting a version by ID."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
        )
        version = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        entry.add_version(version)

        found = entry.get_version("v1")
        assert found == version

        not_found = entry.get_version("v999")
        assert not_found is None

    def test_get_version_by_number(self):
        """Test getting a version by version number."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
        )
        v1 = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        v2 = AgentVersion(
            version_id="v2",
            version_number="2.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        entry.add_version(v1)
        entry.add_version(v2)

        found = entry.get_version_by_number("2.0.0")
        assert found == v2

    def test_get_current_version(self):
        """Test getting the current published version."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
        )
        v1 = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.PUBLISHED,
            definition={},
        )
        v2 = AgentVersion(
            version_id="v2",
            version_number="2.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        entry.add_version(v1)
        entry.add_version(v2)
        entry.current_version = "v1"

        current = entry.get_current_version()
        assert current == v1

    def test_get_current_version_fallback(self):
        """Test fallback to latest published when no current set."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
        )
        v1 = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.PUBLISHED,
            definition={},
        )
        v2 = AgentVersion(
            version_id="v2",
            version_number="2.0.0",
            agent_id="agent1",
            status=VersionStatus.PUBLISHED,
            definition={},
        )
        entry.add_version(v1)
        entry.add_version(v2)
        # No current_version set

        current = entry.get_current_version()
        assert current == v2  # Latest published

    def test_get_latest_version(self):
        """Test getting the latest version regardless of status."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
        )
        v1 = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.PUBLISHED,
            definition={},
        )
        v2 = AgentVersion(
            version_id="v2",
            version_number="2.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={},
        )
        entry.add_version(v1)
        entry.add_version(v2)

        latest = entry.get_latest_version()
        assert latest == v2

    def test_to_dict_and_from_dict(self):
        """Test serialization round trip."""
        entry = AgentCatalogEntry(
            agent_id="agent1",
            tenant_id="tenant1",
            name="Test Agent",
            description="A test agent",
            category="testing",
            tags={"test", "demo"},
            owner_id="user1",
            metadata={"custom": "value"},
        )
        v1 = AgentVersion(
            version_id="v1",
            version_number="1.0.0",
            agent_id="agent1",
            status=VersionStatus.DRAFT,
            definition={"name": "test"},
        )
        entry.add_version(v1)

        data = entry.to_dict()
        restored = AgentCatalogEntry.from_dict(data)

        assert restored.agent_id == entry.agent_id
        assert restored.tenant_id == entry.tenant_id
        assert restored.name == entry.name
        assert restored.description == entry.description
        assert restored.tags == entry.tags
        assert len(restored.versions) == 1


class TestAgentCatalog:
    """Tests for AgentCatalog class."""

    def test_create_agent(self):
        """Test creating an agent in the catalog."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(
            tenant_id="tenant1",
            name="Test Agent",
            description="A test agent",
            category="testing",
            tags={"test"},
            owner_id="user1",
        )
        assert entry.name == "Test Agent"
        assert entry.tenant_id == "tenant1"
        assert entry.agent_id is not None

    def test_create_agent_with_initial_definition(self):
        """Test creating an agent with initial definition creates draft version."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(
            tenant_id="tenant1",
            name="Test Agent",
            initial_definition={"name": "test", "tools": []},
            owner_id="user1",
        )
        assert len(entry.versions) == 1
        assert entry.versions[0].version_number == "0.1.0"
        assert entry.versions[0].status == VersionStatus.DRAFT

    def test_get_agent(self):
        """Test getting an agent by ID."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(
            tenant_id="tenant1",
            name="Test Agent",
        )
        found = catalog.get_agent(entry.agent_id)
        assert found == entry

        not_found = catalog.get_agent("nonexistent")
        assert not_found is None

    def test_list_agents(self):
        """Test listing agents for a tenant."""
        catalog = AgentCatalog()
        catalog.create_agent(tenant_id="tenant1", name="Agent 1", category="cat1")
        catalog.create_agent(tenant_id="tenant1", name="Agent 2", category="cat2")
        catalog.create_agent(tenant_id="tenant2", name="Agent 3", category="cat1")

        # List all for tenant1
        agents = catalog.list_agents("tenant1")
        assert len(agents) == 2

        # Filter by category
        agents = catalog.list_agents("tenant1", category="cat1")
        assert len(agents) == 1
        assert agents[0].name == "Agent 1"

    def test_list_agents_by_tags(self):
        """Test filtering agents by tags."""
        catalog = AgentCatalog()
        catalog.create_agent(
            tenant_id="tenant1", name="Agent 1", tags={"production", "ml"}
        )
        catalog.create_agent(
            tenant_id="tenant1", name="Agent 2", tags={"development"}
        )
        catalog.create_agent(
            tenant_id="tenant1", name="Agent 3", tags={"production", "nlp"}
        )

        agents = catalog.list_agents("tenant1", tags={"production"})
        assert len(agents) == 2

        agents = catalog.list_agents("tenant1", tags={"ml"})
        assert len(agents) == 1
        assert agents[0].name == "Agent 1"

    def test_create_version(self):
        """Test creating a new version for an agent."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(
            tenant_id="tenant1",
            name="Test Agent",
        )
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={"name": "test"},
            created_by="user1",
            changelog="Initial version",
        )
        assert version is not None
        assert version.version_number == "1.0.0"
        assert version.status == VersionStatus.DRAFT
        assert len(entry.versions) == 1

    def test_create_version_nonexistent_agent(self):
        """Test creating version for nonexistent agent returns None."""
        catalog = AgentCatalog()
        version = catalog.create_version(
            agent_id="nonexistent",
            version_number="1.0.0",
            definition={},
        )
        assert version is None

    def test_submit_for_approval(self):
        """Test submitting a version for approval."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )

        result = catalog.submit_for_approval(entry.agent_id, version.version_id)
        assert result is True
        assert version.status == VersionStatus.PENDING_APPROVAL

    def test_submit_for_approval_only_draft(self):
        """Test that only draft versions can be submitted."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )
        # Submit once
        catalog.submit_for_approval(entry.agent_id, version.version_id)
        # Try to submit again
        result = catalog.submit_for_approval(entry.agent_id, version.version_id)
        assert result is False

    def test_approve_version(self):
        """Test approving a version."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )
        catalog.submit_for_approval(entry.agent_id, version.version_id)

        result = catalog.approve_version(
            entry.agent_id, version.version_id, approved_by="admin1"
        )
        assert result is True
        assert version.status == VersionStatus.APPROVED
        assert version.approved_by == "admin1"
        assert version.approved_at is not None

    def test_approve_version_only_pending(self):
        """Test that only pending versions can be approved."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )
        # Still draft, not pending
        result = catalog.approve_version(
            entry.agent_id, version.version_id, approved_by="admin1"
        )
        assert result is False

    def test_reject_version(self):
        """Test rejecting a version."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )
        catalog.submit_for_approval(entry.agent_id, version.version_id)

        result = catalog.reject_version(
            entry.agent_id, version.version_id, reason="Needs more testing"
        )
        assert result is True
        assert version.status == VersionStatus.DRAFT
        assert version.metadata["rejection_reason"] == "Needs more testing"

    def test_publish_version(self):
        """Test publishing a version."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )
        catalog.submit_for_approval(entry.agent_id, version.version_id)
        catalog.approve_version(entry.agent_id, version.version_id, approved_by="admin")

        result = catalog.publish_version(entry.agent_id, version.version_id)
        assert result is True
        assert version.status == VersionStatus.PUBLISHED
        assert version.published_at is not None
        assert entry.current_version == version.version_id

    def test_publish_version_deprecates_previous(self):
        """Test that publishing deprecates the previous published version."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")

        # Create and publish v1
        v1 = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )
        catalog.submit_for_approval(entry.agent_id, v1.version_id)
        catalog.approve_version(entry.agent_id, v1.version_id, approved_by="admin")
        catalog.publish_version(entry.agent_id, v1.version_id)

        # Create and publish v2
        v2 = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="2.0.0",
            definition={},
        )
        catalog.submit_for_approval(entry.agent_id, v2.version_id)
        catalog.approve_version(entry.agent_id, v2.version_id, approved_by="admin")
        catalog.publish_version(entry.agent_id, v2.version_id)

        assert v1.status == VersionStatus.DEPRECATED
        assert v2.status == VersionStatus.PUBLISHED
        assert entry.current_version == v2.version_id

    def test_deprecate_version(self):
        """Test deprecating a published version."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        version = catalog.create_version(
            agent_id=entry.agent_id,
            version_number="1.0.0",
            definition={},
        )
        catalog.submit_for_approval(entry.agent_id, version.version_id)
        catalog.approve_version(entry.agent_id, version.version_id, approved_by="admin")
        catalog.publish_version(entry.agent_id, version.version_id)

        result = catalog.deprecate_version(entry.agent_id, version.version_id)
        assert result is True
        assert version.status == VersionStatus.DEPRECATED
        assert entry.current_version is None

    def test_delete_agent(self):
        """Test deleting an agent from the catalog."""
        catalog = AgentCatalog()
        entry = catalog.create_agent(tenant_id="tenant1", name="Test Agent")
        agent_id = entry.agent_id

        result = catalog.delete_agent(agent_id)
        assert result is True
        assert catalog.get_agent(agent_id) is None

    def test_delete_agent_nonexistent(self):
        """Test deleting nonexistent agent returns False."""
        catalog = AgentCatalog()
        result = catalog.delete_agent("nonexistent")
        assert result is False

    def test_search_agents_by_name(self):
        """Test searching agents by name."""
        catalog = AgentCatalog()
        catalog.create_agent(tenant_id="tenant1", name="Data Processing Agent")
        catalog.create_agent(tenant_id="tenant1", name="ML Training Agent")
        catalog.create_agent(tenant_id="tenant1", name="Report Generator")

        results = catalog.search_agents("tenant1", "agent")
        assert len(results) == 2

        results = catalog.search_agents("tenant1", "data")
        assert len(results) == 1
        assert results[0].name == "Data Processing Agent"

    def test_search_agents_by_description(self):
        """Test searching agents by description."""
        catalog = AgentCatalog()
        catalog.create_agent(
            tenant_id="tenant1",
            name="Agent 1",
            description="Processes customer data",
        )
        catalog.create_agent(
            tenant_id="tenant1",
            name="Agent 2",
            description="Generates reports",
        )

        results = catalog.search_agents("tenant1", "customer")
        assert len(results) == 1
        assert results[0].name == "Agent 1"

    def test_search_agents_by_tags(self):
        """Test searching agents by tags."""
        catalog = AgentCatalog()
        catalog.create_agent(
            tenant_id="tenant1",
            name="Agent 1",
            tags={"machine-learning", "production"},
        )
        catalog.create_agent(
            tenant_id="tenant1",
            name="Agent 2",
            tags={"analytics"},
        )

        results = catalog.search_agents("tenant1", "learning")
        assert len(results) == 1
        assert results[0].name == "Agent 1"

    def test_search_agents_limit(self):
        """Test search limit parameter."""
        catalog = AgentCatalog()
        for i in range(10):
            catalog.create_agent(tenant_id="tenant1", name=f"Test Agent {i}")

        results = catalog.search_agents("tenant1", "test", limit=3)
        assert len(results) == 3
