"""Admin API routes for role management."""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from taskforce.core.interfaces.identity import (
    UserContext,
    Permission,
    Role,
    SYSTEM_ROLES,
    get_permissions_for_roles,
)
from taskforce.api.middleware.auth import (
    get_current_user_dependency,
    require_permission,
)


router = APIRouter(prefix="/admin/roles", tags=["Admin - Roles"])


# Pydantic models for API

class RoleCreate(BaseModel):
    """Request model for creating a role."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    permissions: List[str] = Field(default_factory=list)
    is_system: bool = Field(default=False)


class RoleUpdate(BaseModel):
    """Request model for updating a role."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class RoleResponse(BaseModel):
    """Response model for role data."""

    name: str
    description: str
    permissions: List[str]
    is_system: bool


class RoleListResponse(BaseModel):
    """Response model for role list."""

    roles: List[RoleResponse]
    total: int


class PermissionResponse(BaseModel):
    """Response model for permission data."""

    name: str
    value: str
    description: str


class PermissionListResponse(BaseModel):
    """Response model for permission list."""

    permissions: List[PermissionResponse]
    total: int


# In-memory custom role store for demonstration
# In production, this would use a database
_custom_roles: Dict[str, Role] = {}


def _role_to_response(role: Role) -> RoleResponse:
    """Convert a Role to RoleResponse."""
    return RoleResponse(
        name=role.name,
        description=role.description,
        permissions=[p.value for p in role.permissions],
        is_system=role.is_system,
    )


@router.get("", response_model=RoleListResponse)
async def list_roles(
    include_system: bool = Query(default=True),
    user: UserContext = Depends(require_permission(Permission.ROLE_MANAGE)),
) -> RoleListResponse:
    """List all roles.

    Requires ROLE_MANAGE permission.
    """
    roles = []

    # Add system roles if requested
    if include_system:
        for role in SYSTEM_ROLES.values():
            roles.append(_role_to_response(role))

    # Add custom roles
    for role in _custom_roles.values():
        roles.append(_role_to_response(role))

    return RoleListResponse(
        roles=roles,
        total=len(roles),
    )


@router.post("", response_model=RoleResponse, status_code=201)
async def create_role(
    data: RoleCreate,
    user: UserContext = Depends(require_permission(Permission.ROLE_MANAGE)),
) -> RoleResponse:
    """Create a new custom role.

    Requires ROLE_MANAGE permission.
    System roles cannot be created through this endpoint.
    """
    if data.is_system:
        raise HTTPException(
            status_code=400,
            detail="Cannot create system roles through API",
        )

    if data.name in SYSTEM_ROLES:
        raise HTTPException(
            status_code=409,
            detail=f"Role name '{data.name}' conflicts with system role",
        )

    if data.name in _custom_roles:
        raise HTTPException(
            status_code=409,
            detail=f"Role '{data.name}' already exists",
        )

    # Convert permission strings to Permission enum
    permissions = set()
    for perm_str in data.permissions:
        try:
            permissions.add(Permission(perm_str))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid permission: {perm_str}",
            )

    role = Role(
        name=data.name,
        description=data.description,
        permissions=permissions,
        is_system=False,
    )

    _custom_roles[data.name] = role

    return _role_to_response(role)


@router.get("/permissions", response_model=PermissionListResponse)
async def list_permissions(
    user: UserContext = Depends(require_permission(Permission.ROLE_MANAGE)),
) -> PermissionListResponse:
    """List all available permissions.

    Requires ROLE_MANAGE permission.
    """
    permissions = []
    for perm in Permission:
        # Generate description from permission name
        description = perm.name.replace("_", " ").title()
        permissions.append(
            PermissionResponse(
                name=perm.name,
                value=perm.value,
                description=description,
            )
        )

    return PermissionListResponse(
        permissions=permissions,
        total=len(permissions),
    )


@router.get("/{role_name}", response_model=RoleResponse)
async def get_role(
    role_name: str,
    user: UserContext = Depends(require_permission(Permission.ROLE_MANAGE)),
) -> RoleResponse:
    """Get a role by name.

    Requires ROLE_MANAGE permission.
    """
    # Check system roles first
    if role_name in SYSTEM_ROLES:
        return _role_to_response(SYSTEM_ROLES[role_name])

    # Check custom roles
    if role_name in _custom_roles:
        return _role_to_response(_custom_roles[role_name])

    raise HTTPException(status_code=404, detail="Role not found")


@router.put("/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    data: RoleUpdate,
    user: UserContext = Depends(require_permission(Permission.ROLE_MANAGE)),
) -> RoleResponse:
    """Update a role.

    Requires ROLE_MANAGE permission.
    System roles cannot be modified.
    """
    # Cannot modify system roles
    if role_name in SYSTEM_ROLES:
        raise HTTPException(
            status_code=403,
            detail="System roles cannot be modified",
        )

    if role_name not in _custom_roles:
        raise HTTPException(status_code=404, detail="Role not found")

    existing = _custom_roles[role_name]

    # Convert permission strings if provided
    permissions = existing.permissions
    if data.permissions is not None:
        permissions = set()
        for perm_str in data.permissions:
            try:
                permissions.add(Permission(perm_str))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid permission: {perm_str}",
                )

    # Handle name change
    new_name = data.name if data.name is not None else existing.name
    if new_name != role_name:
        if new_name in SYSTEM_ROLES or new_name in _custom_roles:
            raise HTTPException(
                status_code=409,
                detail=f"Role name '{new_name}' already exists",
            )
        del _custom_roles[role_name]

    updated = Role(
        name=new_name,
        description=data.description if data.description is not None else existing.description,
        permissions=permissions,
        is_system=False,
    )

    _custom_roles[new_name] = updated

    return _role_to_response(updated)


@router.delete("/{role_name}", status_code=204)
async def delete_role(
    role_name: str,
    user: UserContext = Depends(require_permission(Permission.ROLE_MANAGE)),
) -> None:
    """Delete a role.

    Requires ROLE_MANAGE permission.
    System roles cannot be deleted.
    """
    if role_name in SYSTEM_ROLES:
        raise HTTPException(
            status_code=403,
            detail="System roles cannot be deleted",
        )

    if role_name not in _custom_roles:
        raise HTTPException(status_code=404, detail="Role not found")

    del _custom_roles[role_name]
