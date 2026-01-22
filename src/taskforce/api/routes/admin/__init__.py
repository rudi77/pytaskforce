"""Admin API routes for enterprise management."""

from taskforce.api.routes.admin.tenants import router as tenants_router
from taskforce.api.routes.admin.users import router as users_router
from taskforce.api.routes.admin.roles import router as roles_router

__all__ = ["tenants_router", "users_router", "roles_router"]
