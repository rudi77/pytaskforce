"""Admin API routes for user management."""

from typing import Optional, List, Dict, Any, Set
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from taskforce.core.interfaces.identity import (
    UserContext,
    Permission,
    get_permissions_for_roles,
)
from taskforce.api.middleware.auth import (
    get_current_user_dependency,
    require_permission,
)


router = APIRouter(prefix="/admin/users", tags=["Admin - Users"])


# Pydantic models for API

class UserCreate(BaseModel):
    """Request model for creating a user."""

    username: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)


class UserUpdate(BaseModel):
    """Request model for updating a user."""

    username: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = None
    roles: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None


class UserResponse(BaseModel):
    """Response model for user data."""

    user_id: str
    tenant_id: str
    username: str
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class UserListResponse(BaseModel):
    """Response model for user list."""

    users: List[UserResponse]
    total: int
    limit: int
    offset: int


# In-memory user store for demonstration
_users: Dict[str, Dict[str, UserContext]] = {}  # tenant_id -> user_id -> user


@router.get("", response_model=UserListResponse)
async def list_users(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: UserContext = Depends(require_permission(Permission.USER_MANAGE)),
) -> UserListResponse:
    """List users in the current tenant.

    Requires USER_MANAGE permission.
    """
    tenant_users = _users.get(user.tenant_id, {})
    users = list(tenant_users.values())
    total = len(users)
    paginated = users[offset : offset + limit]

    return UserListResponse(
        users=[
            UserResponse(
                user_id=u.user_id,
                tenant_id=u.tenant_id,
                username=u.username,
                email=u.email,
                roles=list(u.roles),
                permissions=[p.value for p in u.permissions],
                attributes=u.attributes,
            )
            for u in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    user: UserContext = Depends(require_permission(Permission.USER_MANAGE)),
) -> UserResponse:
    """Create a new user in the current tenant.

    Requires USER_MANAGE permission.
    """
    import uuid

    user_id = str(uuid.uuid4())
    roles = set(data.roles)
    permissions = get_permissions_for_roles(roles)

    new_user = UserContext(
        user_id=user_id,
        tenant_id=user.tenant_id,
        username=data.username,
        email=data.email,
        roles=roles,
        permissions=permissions,
        attributes=data.attributes or {},
    )

    if user.tenant_id not in _users:
        _users[user.tenant_id] = {}
    _users[user.tenant_id][user_id] = new_user

    return UserResponse(
        user_id=new_user.user_id,
        tenant_id=new_user.tenant_id,
        username=new_user.username,
        email=new_user.email,
        roles=list(new_user.roles),
        permissions=[p.value for p in new_user.permissions],
        attributes=new_user.attributes,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    user: UserContext = Depends(require_permission(Permission.USER_MANAGE)),
) -> UserResponse:
    """Get a user by ID.

    Requires USER_MANAGE permission.
    """
    tenant_users = _users.get(user.tenant_id, {})
    target_user = tenant_users.get(user_id)

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        user_id=target_user.user_id,
        tenant_id=target_user.tenant_id,
        username=target_user.username,
        email=target_user.email,
        roles=list(target_user.roles),
        permissions=[p.value for p in target_user.permissions],
        attributes=target_user.attributes,
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    data: UserUpdate,
    user: UserContext = Depends(require_permission(Permission.USER_MANAGE)),
) -> UserResponse:
    """Update a user.

    Requires USER_MANAGE permission.
    """
    tenant_users = _users.get(user.tenant_id, {})
    target_user = tenant_users.get(user_id)

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Calculate new roles and permissions
    roles = set(data.roles) if data.roles is not None else target_user.roles
    permissions = get_permissions_for_roles(roles)

    # Create updated user (UserContext is frozen)
    updated = UserContext(
        user_id=target_user.user_id,
        tenant_id=target_user.tenant_id,
        username=data.username if data.username is not None else target_user.username,
        email=data.email if data.email is not None else target_user.email,
        roles=roles,
        permissions=permissions,
        attributes={**target_user.attributes, **(data.attributes or {})},
    )

    _users[user.tenant_id][user_id] = updated

    return UserResponse(
        user_id=updated.user_id,
        tenant_id=updated.tenant_id,
        username=updated.username,
        email=updated.email,
        roles=list(updated.roles),
        permissions=[p.value for p in updated.permissions],
        attributes=updated.attributes,
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: UserContext = Depends(require_permission(Permission.USER_MANAGE)),
) -> None:
    """Delete a user.

    Requires USER_MANAGE permission.
    """
    tenant_users = _users.get(user.tenant_id, {})

    if user_id not in tenant_users:
        raise HTTPException(status_code=404, detail="User not found")

    del tenant_users[user_id]
