import { useQuery } from "@tanstack/react-query";
import { Badge } from "@taskforce/ui-shell";

import { adminApi, type Tenant } from "../api/admin";
import { DataTable, type ColumnDef } from "../components/DataTable";
import { PageShell, SectionCard } from "../components/PageShell";

const COLUMNS: ColumnDef<Tenant>[] = [
  { key: "name", header: "Name", cell: (t) => <span className="font-medium">{t.name}</span> },
  { key: "plan", header: "Plan", cell: (t) => t.plan },
  {
    key: "status",
    header: "Status",
    cell: (t) => (
      <Badge variant={t.status === "active" ? "success" : t.status === "trial" ? "secondary" : "destructive"}>
        {t.status}
      </Badge>
    ),
  },
  {
    key: "members",
    header: "Members",
    cell: (t) => t.member_count ?? "—",
    className: "tabular-nums",
  },
  {
    key: "created",
    header: "Created",
    cell: (t) => new Date(t.created_at).toLocaleDateString(),
  },
];

export default function TenantsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["enterprise", "tenants"],
    queryFn: () => adminApi.listTenants(),
  });

  return (
    <PageShell
      title="Tenants"
      description="Multi-tenant organizations enrolled with this Taskforce instance."
    >
      <SectionCard>
        <DataTable
          columns={COLUMNS}
          rows={data?.items}
          isLoading={isLoading}
          rowKey={(t) => t.id}
          emptyState="No tenants registered yet."
        />
      </SectionCard>
    </PageShell>
  );
}
