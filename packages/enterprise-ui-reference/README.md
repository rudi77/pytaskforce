# @taskforce/enterprise-ui — Reference Implementation

This directory is a **reference implementation** of the Taskforce
Enterprise UI plugin. It lives in `pytaskforce` so the contract and
the host integration can be developed and verified together. The
**production home** of this package is the
[`taskforce-enterprise`](https://github.com/rudi77/taskforce-enterprise)
repository (typically as a `web/` subdirectory).

## What this package does

Contributes five admin pages to the pytaskforce management UI:

| Path | Capability flag | Required role(s) |
|---|---|---|
| `/admin/tenants` | `admin.tenants` | `admin` |
| `/admin/users` | `admin.users` | `admin` |
| `/admin/audit` | `admin.audit` | `admin`, `auditor` |
| `/admin/catalog` | `agents.catalog` | `admin`, `agent_owner` |
| `/admin/approvals` | `agents.approvals` | `admin`, `approver` |

Each entry only appears in the host sidebar if the backend's
`GET /api/v1/ui/manifest` reports the matching capability flag,
and each page additionally enforces RBAC via the host's
`<RequireRole>` guard.

## Architecture

```
@taskforce/ui-shell                @taskforce/enterprise-ui
─ Tailwind preset                  ─ enterpriseUIPlugin
─ shadcn primitives        ◄───────  (UIPlugin shape: id, navItems,
─ apiFetch + ApiError                routes, capabilities)
─ Plugin contract types            ─ register(registry)
                                   ─ TenantsPage / UsersRolesPage / …
        ▲
        │ peerDependency on both sides
        │
        ▼
pytaskforce/ui (host)
  ─ ui/src/plugins/loader.ts
        try { import("@taskforce/enterprise-ui") } catch {}
  ─ AppShell merges plugin navItems into the "Admin" section
  ─ <CapabilityGuard> + <RequireRole> wrap every plugin route
```

The host (pytaskforce/ui) bundles this package only when
`@taskforce/enterprise-ui` is listed in its `optionalDependencies`
and successfully resolves at install time. If absent, the import
fails silently and the admin pages simply do not exist in the
bundle.

## How to copy this into `taskforce-enterprise`

1. Copy this whole directory into the enterprise repo, typically as
   `web/`:

   ```bash
   cp -r pytaskforce/packages/enterprise-ui-reference  taskforce-enterprise/web
   ```

2. In `taskforce-enterprise/web/package.json`:
   - Set `"private": false` (or leave private until ready to publish).
   - Replace the `devDependencies["@taskforce/ui-shell"]` `file:` link
     with a real npm version range, e.g.
     `"@taskforce/ui-shell": "^0.1.0"`.
   - Bump the version on every release together with the Python
     plugin so `min_ui_version` checks remain in sync.

3. In `taskforce_enterprise/integration/plugin.py`, implement
   `EnterprisePlugin.get_ui_manifest()` to return:

   ```python
   {
     "id": "enterprise",
     "version": __version__,
     "display_name": "Taskforce Enterprise",
     "capabilities": [
       "admin.tenants",
       "admin.users",
       "admin.audit",
       "agents.catalog",
       "agents.approvals",
     ],
     "npm_package": "@taskforce/enterprise-ui",
     "min_ui_version": ">=0.1.0,<1.0.0",
   }
   ```

4. Publish `@taskforce/enterprise-ui` to npm (or a private registry).

5. Operators who want enterprise UI:
   - `pip install taskforce-enterprise` — backend features.
   - In their `pytaskforce/ui` build, add
     `"@taskforce/enterprise-ui": "^0.1.0"` to
     `optionalDependencies`, run `npm install`, and rebuild the UI.
   - The pages appear automatically.

## How to develop locally

This reference implementation is consumable as-is via npm `file:`
links. From the pytaskforce checkout:

```bash
# 1. Build ui-shell once so its dist/ exists.
cd packages/ui-shell && npm install && npm run build

# 2. Build the enterprise reference.
cd ../enterprise-ui-reference && npm install && npm run build

# 3. Wire it into the host UI: edit ui/package.json
#    "optionalDependencies": {
#      "@taskforce/enterprise-ui": "file:../packages/enterprise-ui-reference"
#    }
#    Then in ui/, npm install + npm run build.
```

For a real dev loop, prefer `npm link` between the three packages so
HMR works on edits.

## Backend API expectations

Pages call helpers in `src/api/admin.ts`. Each helper is tolerant of
404/501 responses and returns an empty list — so the UI renders
"empty state" rather than crashing while a particular endpoint is
still in development.

| Helper | Endpoint | Shape |
|---|---|---|
| `listTenants` | `GET /api/v1/admin/tenants` | `{ items: Tenant[] }` |
| `listUsers` | `GET /api/v1/admin/users` | `{ items: User[] }` |
| `listAuditEntries` | `GET /api/v1/admin/audit` | `{ items: AuditEntry[] }` |
| `listCatalogAgents` | `GET /api/v1/admin/catalog/agents` | `{ items: CatalogAgent[] }` |
| `listApprovals` | `GET /api/v1/admin/approvals` | `{ items: ApprovalRequest[] }` |

Adjust the shapes in `src/api/admin.ts` to match the exact
`taskforce_enterprise.api.routes.admin` response payloads.

## Why this lives here for now

Because the git scope used to bootstrap this work was restricted to
`rudi77/pytaskforce`. Everything in this directory is designed to be
moved to the enterprise repo without changes — only the `package.json`
needs minor tweaks (npm versions instead of file links, `private:
false`).
