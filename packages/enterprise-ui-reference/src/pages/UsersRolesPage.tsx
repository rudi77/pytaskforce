import { useQuery } from "@tanstack/react-query";
import { Badge } from "@taskforce/ui-shell";

import { adminApi, type User } from "../api/admin";
import { DataTable, type ColumnDef } from "../components/DataTable";
import { PageShell, SectionCard } from "../components/PageShell";

const COLUMNS: ColumnDef<User>[] = [
  {
    key: "user",
    header: "User",
    cell: (u) => (
      <div>
        <div className="font-medium">{u.display_name ?? u.email}</div>
        {u.display_name ? (
          <div className="text-xs text-muted-foreground">{u.email}</div>
        ) : null}
      </div>
    ),
  },
  {
    key: "roles",
    header: "Roles",
    cell: (u) => (
      <div className="flex flex-wrap gap-1">
        {u.roles.length === 0 ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          u.roles.map((role) => (
            <Badge key={role} variant="secondary">
              {role}
            </Badge>
          ))
        )}
      </div>
    ),
  },
  {
    key: "tenant",
    header: "Tenant",
    cell: (u) => u.tenant_id,
  },
  {
    key: "last_login",
    header: "Last login",
    cell: (u) => (u.last_login ? new Date(u.last_login).toLocaleString() : "—"),
  },
];

export default function UsersRolesPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["enterprise", "users"],
    queryFn: () => adminApi.listUsers(),
  });

  return (
    <PageShell
      title="Users & Roles"
      description="Identities and role-based access control across all tenants."
    >
      <SectionCard>
        <DataTable
          columns={COLUMNS}
          rows={data?.items}
          isLoading={isLoading}
          rowKey={(u) => u.id}
          emptyState="No users yet."
        />
      </SectionCard>
    </PageShell>
  );
}
