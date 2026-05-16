---
feature: cowork
status: shipped
since: 2026-05-15
last_verified: 2026-05-16
owner: rudi77
---

# CoWork — Per-Project Workspaces

A user organises work into projects. Each project is a directory the user
owns; taskforce remembers the project in a small registry and, when a
conversation is bound to that project, runs the agent with its working
directory rooted at the project's path. Conversations without a project
keep working with the global work directory — projects are opt-in.

## Capabilities (what the user can do)

- create a project from scratch (taskforce creates the directory) OR by importing an existing directory
- list all projects, newest first
- look up a single project by id
- remove a project from the registry without losing the on-disk files
- bind a new conversation to a project so the agent runs in that project's folder
- filter the conversations list by project

## Invariants (what must always be true)

- Two projects cannot point at the same on-disk directory; conflicting create attempts return a clear error, never silent overwrite.
- Removing a project from the registry never deletes the user's files on disk.
- Every project directory contains at minimum a `CLAUDE.md` and a `skills/` folder — taskforce creates them when missing, but never overwrites them when present.
- Concurrent create attempts for the same path cannot both succeed; conflict detection is process-wide, not per-request.
- Conversations without a `project_id` are fully usable; project binding is strictly opt-in.
- When a conversation has a `project_id`, the agent's working directory IS that project's path (not the global `TASKFORCE_WORK_DIR`).
- The conversations list can be filtered by `project_id`; unfiltered, all conversations remain visible regardless of project membership.

## API surface (the contract clients depend on)

- POST /api/v1/projects → 201 created
- POST /api/v1/projects → 409 on duplicate path
- POST /api/v1/projects → 400 on invalid path (empty, mode=existing with missing dir, or non-directory)
- GET  /api/v1/projects → 200 (list, newest first)
- GET  /api/v1/projects/{project_id} → 200
- GET  /api/v1/projects/{project_id} → 404 if missing
- DELETE /api/v1/projects/{project_id} → 204
- DELETE /api/v1/projects/{project_id} → 404 if missing
- POST /api/v1/conversations accepts optional `project_id` in body
- GET  /api/v1/conversations accepts `project_id` as query filter

## Extension points

- `set_project_store_override` — enterprise plugins replace the default file-backed registry with a tenant-scoped store. Resolved per-request (not cached), so installs and uninstalls take effect immediately.

## Tests (must exist and pass)

- spec("cowork.create_scratch_creates_anchors")
- spec("cowork.create_existing_rejects_missing_dir")
- spec("cowork.create_duplicate_path_returns_409")
- spec("cowork.delete_keeps_directory")
- spec("cowork.concurrent_create_serialized")
- spec("cowork.conversation_with_project_id_routes_to_project_path")
- spec("cowork.conversation_without_project_id_uses_global_workdir")
- spec("cowork.list_filtered_by_project_id")

## Known gaps

- No archive endpoint — today the user either deletes (registry-only) or leaves a project alone. The cowork-comparison vision document hints at archive semantics, but they are not in the contract.
- Project deletion does not cascade to conversations. A conversation pointing at a deleted project will fail to resolve its working directory on the next execution.
- No project-level ownership or transfer. Multi-tenant scoping happens at the store level (via the override hook); per-project transfer between users is not modeled.
- No backend `@pytest.mark.spec` markers exist yet — the Tests section above asserts the target, not current state. The UI test (`ProjectDetailPage.test.tsx`) exists but is not yet marked.

## Cross-references

- related_spec: conversations.md
- related_spec: multi-tenant.md
- docs: docs/cowork-comparison.md (vision and gap analysis, not contract)
- commit: 345abec (introduced 2026-05-15)
