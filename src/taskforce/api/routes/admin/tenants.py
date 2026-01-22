"""Admin API routes for tenant management."""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from taskforce.core.interfaces.identity import (
    TenantContext,
    UserContext,
    Permission,
)
from taskforce.api.middleware.auth import (
    get_current_user_dependency,
    require_permission,
)


router = APIRouter(prefix="/admin/tenants", tags=["Admin - Tenants"])


# Pydantic models for API

class TenantCreate(BaseModel):
    """Request model for creating a tenant."""

    name: str = Field(..., min_length=1, max_length=255)
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    """Request model for updating a tenant."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    settings: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class TenantResponse(BaseModel):
    """Response model for tenant data."""

    tenant_id: str
    name: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class TenantListResponse(BaseModel):
    """Response model for tenant list."""

    tenants: List[TenantResponse]
    total: int
    limit: int
    offset: int


# In-memory tenant store for demonstration
# In production, this would use a database
_tenants: Dict[str, TenantContext] = {}


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: UserContext = Depends(require_permission(Permission.TENANT_MANAGE)),
) -> TenantListResponse:
    """List all tenants.

    Requires TENANT_MANAGE permission.
    """
    tenants = list(_tenants.values())
    total = len(tenants)
    paginated = tenants[offset : offset + limit]

    return TenantListResponse(
        tenants=[
            TenantResponse(
                tenant_id=t.tenant_id,
                name=t.name,
                settings=t.settings,
                metadata=t.metadata,
                created_at=t.created_at.isoformat() if t.created_at else None,
            )
            for t in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    data: TenantCreate,
    user: UserContext = Depends(require_permission(Permission.TENANT_MANAGE)),
) -> TenantResponse:
    """Create a new tenant.

    Requires TENANT_MANAGE permission.
    """
    import uuid
    from datetime import datetime, timezone

    tenant_id = str(uuid.uuid4())

    tenant = TenantContext(
        tenant_id=tenant_id,
        name=data.name,
        settings=data.settings or {},
        metadata=data.metadata or {},
        created_at=datetime.now(timezone.utc),
    )

    _tenants[tenant_id] = tenant

    return TenantResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        settings=tenant.settings,
        metadata=tenant.metadata,
        created_at=tenant.created_at.isoformat() if tenant.created_at else None,
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    user: UserContext = Depends(require_permission(Permission.TENANT_MANAGE)),
) -> TenantResponse:
    """Get a tenant by ID.

    Requires TENANT_MANAGE permission.
    """
    tenant = _tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return TenantResponse(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        settings=tenant.settings,
        metadata=tenant.metadata,
        created_at=tenant.created_at.isoformat() if tenant.created_at else None,
    )


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    data: TenantUpdate,
    user: UserContext = Depends(require_permission(Permission.TENANT_MANAGE)),
) -> TenantResponse:
    """Update a tenant.

    Requires TENANT_MANAGE permission.
    """
    tenant = _tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Create updated tenant (TenantContext is frozen)
    updated = TenantContext(
        tenant_id=tenant.tenant_id,
        name=data.name if data.name is not None else tenant.name,
        settings={**tenant.settings, **(data.settings or {})},
        metadata={**tenant.metadata, **(data.metadata or {})},
        created_at=tenant.created_at,
    )

    _tenants[tenant_id] = updated

    return TenantResponse(
        tenant_id=updated.tenant_id,
        name=updated.name,
        settings=updated.settings,
        metadata=updated.metadata,
        created_at=updated.created_at.isoformat() if updated.created_at else None,
    )


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: str,
    user: UserContext = Depends(require_permission(Permission.TENANT_MANAGE)),
) -> None:
    """Delete a tenant.

    Requires TENANT_MANAGE permission.
    """
    if tenant_id not in _tenants:
        raise HTTPException(status_code=404, detail="Tenant not found")

    del _tenants[tenant_id]
