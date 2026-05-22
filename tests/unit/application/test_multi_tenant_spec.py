"""Spec-coverage tests for the multi-tenant framework contract.

Covers the two structural claims in ``docs/spec/multi-tenant.md`` that
need their own test: the framework never imports the enterprise plugin,
and the identity protocol stubs are runtime-checkable.

Spec: docs/spec/multi-tenant.md — tests tagged @pytest.mark.spec("multi-tenant.*").
"""

from __future__ import annotations

from pathlib import Path

import pytest

import taskforce


@pytest.mark.spec("multi-tenant.framework_has_no_taskforce_enterprise_import")
def test_framework_has_no_taskforce_enterprise_import() -> None:
    """No framework module imports ``taskforce_enterprise``.

    Multi-tenancy is realised by the separate enterprise plugin through
    override hooks — the framework must never depend on it directly.
    """
    framework_root = Path(taskforce.__file__).resolve().parent
    offenders: list[str] = []

    for py_file in framework_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if (
                "import taskforce_enterprise" in stripped
                or stripped.startswith("from taskforce_enterprise")
            ):
                offenders.append(f"{py_file.relative_to(framework_root)}: {stripped}")

    assert offenders == [], "framework must not import taskforce_enterprise:\n" + "\n".join(
        offenders
    )


@pytest.mark.spec("multi-tenant.identity_stubs_are_runtime_checkable")
def test_identity_stubs_are_runtime_checkable() -> None:
    """The identity protocol stubs are ``@runtime_checkable`` Protocols.

    The framework type-annotates against them and uses ``isinstance``
    fallbacks without importing the enterprise plugin's concrete types.
    """
    from taskforce.core.interfaces.identity_stubs import (
        AnonymousUser,
        DefaultTenant,
        IdentityProviderProtocol,
        PolicyEngineProtocol,
        TenantContextProtocol,
        TenantResolverProtocol,
        UserContextProtocol,
    )

    protocols = [
        TenantContextProtocol,
        UserContextProtocol,
        IdentityProviderProtocol,
        PolicyEngineProtocol,
        TenantResolverProtocol,
    ]
    for proto in protocols:
        # @runtime_checkable sets this marker; without it isinstance raises.
        assert getattr(proto, "_is_runtime_protocol", False) is True, proto

    # isinstance against a runtime-checkable Protocol must not raise …
    assert isinstance(DefaultTenant(), TenantContextProtocol)
    assert isinstance(AnonymousUser(), UserContextProtocol)
    # … and a structurally-unrelated object is simply not an instance.
    assert not isinstance(object(), TenantContextProtocol)
