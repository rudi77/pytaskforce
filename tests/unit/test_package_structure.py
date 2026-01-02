"""Test that the package structure is correctly set up."""

import pytest


def test_taskforce_imports():
    """Test that core taskforce modules can be imported."""
    import taskforce
    from taskforce import __version__
    
    assert __version__ == "0.1.0"


def test_core_layer_imports():
    """Test that core layer modules can be imported."""
    import taskforce.core
    import taskforce.core.domain
    import taskforce.core.interfaces
    import taskforce.core.prompts


def test_infrastructure_layer_imports():
    """Test that infrastructure layer modules can be imported."""
    import taskforce.infrastructure
    import taskforce.infrastructure.persistence
    import taskforce.infrastructure.llm
    import taskforce.infrastructure.tools
    import taskforce.infrastructure.tools.native
    import taskforce.infrastructure.tools.rag
    import taskforce.infrastructure.tools.mcp
    import taskforce.infrastructure.memory


def test_application_layer_imports():
    """Test that application layer modules can be imported."""
    import taskforce.application


def test_api_layer_imports():
    """Test that API layer modules can be imported."""
    import taskforce.api
    import taskforce.api.routes
    import taskforce.api.cli

