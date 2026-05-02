/**
 * Thin wrappers around the enterprise plugin's `/api/v1/admin/*`
 * endpoints. Every helper uses the shared `apiFetch` from
 * `@taskforce/ui-shell`, which the host configures with the active
 * base URL + bearer token at startup.
 *
 * The shapes below mirror the typical enterprise feature-set
 * documented in `docs/features/enterprise.md`. Adjust them to match
 * the actual backend response when wiring this package against
 * `taskforce-enterprise`.
 */
import { apiFetch, ApiError } from "@taskforce/ui-shell";

export interface Tenant {
  id: string;
  name: string;
  plan: string;
  status: "active" | "suspended" | "trial";
  created_at: string;
  member_count?: number;
}

export interface User {
  id: string;
  email: string;
  display_name?: string;
  roles: string[];
  tenant_id: string;
  last_login?: string | null;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  resource: string;
  outcome: "success" | "failure";
  details?: Record<string, unknown>;
}

export interface CatalogAgent {
  id: string;
  name: string;
  current_version: string;
  status:
    | "draft"
    | "pending_approval"
    | "approved"
    | "published"
    | "deprecated"
    | "archived";
  owner: string;
  updated_at: string;
}

export interface ApprovalRequest {
  id: string;
  resource_type: "agent" | "skill" | "config";
  resource_id: string;
  requested_by: string;
  requested_at: string;
  status: "pending" | "approved" | "rejected" | "expired";
  reviewers: string[];
}

interface List<T> {
  items: T[];
  total?: number;
}

/**
 * Read helper that swallows 404 / 501 from the backend by returning an
 * empty list. The enterprise plugin may ship some endpoints later than
 * others; missing endpoints surface as an empty state rather than a
 * red screen.
 */
async function listOrEmpty<T>(path: string): Promise<List<T>> {
  try {
    return await apiFetch<List<T>>(path);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 501)) {
      return { items: [], total: 0 };
    }
    throw error;
  }
}

export const adminApi = {
  listTenants: () => listOrEmpty<Tenant>("/api/v1/admin/tenants"),
  listUsers: () => listOrEmpty<User>("/api/v1/admin/users"),
  listAuditEntries: () => listOrEmpty<AuditEntry>("/api/v1/admin/audit"),
  listCatalogAgents: () => listOrEmpty<CatalogAgent>("/api/v1/admin/catalog/agents"),
  listApprovals: () => listOrEmpty<ApprovalRequest>("/api/v1/admin/approvals"),
};
