"""
Profile API Routes
==================

Read-only discovery endpoints for the management UI:

* ``GET /api/v1/profiles`` — list every profile across the framework and
  installed agent packages.
* ``GET /api/v1/profiles/{name}`` — return parsed config + raw YAML text.
* ``GET /api/v1/profiles/available-as-subagent`` — same shape as the list
  endpoint but excludes the requested parent profile, intended for the
  sub-agent dropdown in the agent editor.

Write/update endpoints arrive in Phase 3.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from taskforce.api.dependencies import require_permission
from taskforce.api.errors import http_exception as _http_exception
from taskforce.api.schemas.profile_schemas import (
    ProfileClonePayload,
    ProfileCreatePayload,
    ProfileDefinitionPayload,
    ProfileDetail,
    ProfileListResponse,
    ProfileSummary,
)
from taskforce.application.profile_loader import ProfileLoader
from taskforce.application.profile_writer import (
    ProfileExists,
    ProfileNotFound,
    ProfileReadOnly,
    ProfileWriteError,
    ProfileWriter,
)

router = APIRouter()


def _summary_from_dict(entry: dict) -> ProfileSummary:
    return ProfileSummary(
        name=entry["name"],
        path=entry["path"],
        format=entry["format"],
        description=entry.get("description") or "",
        specialist=entry.get("specialist"),
        name_label=entry.get("name_label"),
        is_custom=bool(entry.get("is_custom")),
    )


@router.get(
    "/profiles",
    response_model=ProfileListResponse,
    summary="List all profiles",
)
def list_profiles(
    _permission: None = Depends(require_permission("agent:read")),
) -> ProfileListResponse:
    """Discover every profile available to the running server."""
    loader = ProfileLoader()
    summaries = [_summary_from_dict(entry) for entry in loader.list_profiles()]
    return ProfileListResponse(profiles=summaries)


@router.get(
    "/profiles/available-as-subagent",
    response_model=ProfileListResponse,
    summary="List profiles usable as a sub-agent",
)
def list_subagent_candidates(
    exclude: str | None = Query(
        None,
        description="Profile name to exclude (typically the agent being edited)",
    ),
    _permission: None = Depends(require_permission("agent:read")),
) -> ProfileListResponse:
    """Return the same profile catalog minus an optional parent profile."""
    loader = ProfileLoader()
    summaries = [
        _summary_from_dict(entry)
        for entry in loader.list_profiles()
        if entry["name"] != exclude
    ]
    return ProfileListResponse(profiles=summaries)


@router.get(
    "/profiles/{name}",
    response_model=ProfileDetail,
    summary="Get a profile by name",
)
def get_profile(
    name: str,
    _permission: None = Depends(require_permission("agent:read")),
) -> ProfileDetail:
    """Return the parsed config and the original source text for ``name``."""
    loader = ProfileLoader()
    writer = ProfileWriter(loader=loader)
    try:
        config, raw_text, path = loader.load_with_raw(name)
    except FileNotFoundError as exc:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="profile_not_found",
            message=str(exc),
        ) from exc

    fmt = "agent_md" if path.name.endswith(".agent.md") else "yaml"
    return ProfileDetail(
        name=name,
        path=str(path),
        format=fmt,
        description=str(config.get("description") or "").strip(),
        specialist=config.get("specialist"),
        is_writable=writer.is_writable(name),
        config=config,
        yaml_text=raw_text,
    )


@router.post(
    "/profiles",
    response_model=ProfileDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user profile",
)
def create_profile(
    payload: ProfileCreatePayload,
    _permission: None = Depends(require_permission("agent:create")),
) -> ProfileDetail:
    """Persist a new YAML profile to the user-profiles directory."""
    writer = ProfileWriter()
    try:
        path = writer.create(payload.name, payload.config)
    except ProfileExists as exc:
        raise _http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="profile_exists",
            message=str(exc),
        ) from exc
    except (ProfileWriteError, ValueError) as exc:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="profile_invalid",
            message=str(exc),
        ) from exc

    return _detail_for(payload.name, path)


@router.put(
    "/profiles/{name}",
    response_model=ProfileDetail,
    summary="Update a user profile",
)
def update_profile(
    name: str,
    payload: ProfileDefinitionPayload,
    _permission: None = Depends(require_permission("agent:update")),
) -> ProfileDetail:
    """Overwrite a user-owned YAML profile while preserving comments."""
    writer = ProfileWriter()
    try:
        path = writer.update(name, payload.config)
    except ProfileNotFound as exc:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="profile_not_found",
            message=str(exc),
        ) from exc
    except ProfileReadOnly as exc:
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="profile_read_only",
            message=str(exc),
        ) from exc
    except (ProfileWriteError, ValueError) as exc:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="profile_invalid",
            message=str(exc),
        ) from exc

    return _detail_for(name, path)


# Profile names that ship with the framework or its bundled agent packages.
# The user-profiles directory wins by precedence, so allowing a clone to
# shadow ``default`` / ``butler`` / ``coding_agent`` / ``rag_agent``
# silently changes which profile users get when they say ``--profile butler``.
# Block the obvious cases at clone time.
_RESERVED_TARGET_NAMES: frozenset[str] = frozenset(
    {
        "default",
        "butler",
        "coding_agent",
        "coding-agent",
        "rag_agent",
        "rag-agent",
        "llm_config",
        "pricing",
        "defaults",
    }
)


@router.post(
    "/profiles/{source}/clone",
    response_model=ProfileDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Clone a (read-only) profile into the user-profiles directory",
)
def clone_profile(
    source: str,
    payload: ProfileClonePayload,
    _permission: None = Depends(require_permission("agent:create")),
) -> ProfileDetail:
    """Copy ``source`` into the user-profiles directory under ``target_name``.

    Lets the UI customize butler / coding_agent / rag_agent profiles without
    touching the read-only files shipped by the agent packages.
    """
    if payload.target_name in _RESERVED_TARGET_NAMES:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="profile_name_reserved",
            message=(
                f"'{payload.target_name}' is reserved by the framework or a "
                "bundled agent package. Choose a different name (e.g. "
                f"'{payload.target_name}-copy')."
            ),
        )
    loader = ProfileLoader()
    writer = ProfileWriter(loader=loader)
    try:
        config, _raw, _path = loader.load_with_raw(source)
    except FileNotFoundError as exc:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="profile_not_found",
            message=str(exc),
        ) from exc
    try:
        path = writer.create(payload.target_name, config)
    except ProfileExists as exc:
        raise _http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="profile_exists",
            message=str(exc),
        ) from exc
    except (ProfileWriteError, ValueError) as exc:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="profile_invalid",
            message=str(exc),
        ) from exc
    return _detail_for(payload.target_name, path)


@router.delete(
    "/profiles/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user profile",
)
def delete_profile(
    name: str,
    _permission: None = Depends(require_permission("agent:delete")),
) -> Response:
    writer = ProfileWriter()
    try:
        writer.delete(name)
    except ProfileNotFound as exc:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="profile_not_found",
            message=str(exc),
        ) from exc
    except ProfileReadOnly as exc:
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="profile_read_only",
            message=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _detail_for(name: str, path) -> ProfileDetail:
    loader = ProfileLoader()
    writer = ProfileWriter(loader=loader)
    config, raw_text, resolved = loader.load_with_raw(name)
    fmt = "agent_md" if resolved.name.endswith(".agent.md") else "yaml"
    return ProfileDetail(
        name=name,
        path=str(resolved),
        format=fmt,
        description=str(config.get("description") or "").strip(),
        specialist=config.get("specialist"),
        is_writable=writer.is_writable(name),
        config=config,
        yaml_text=raw_text,
    )
