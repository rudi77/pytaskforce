import { useQuery } from "@tanstack/react-query";
import { Badge } from "@taskforce/ui-shell";

import { adminApi, type CatalogAgent } from "../api/admin";
import { DataTable, type ColumnDef } from "../components/DataTable";
import { PageShell, SectionCard } from "../components/PageShell";

type Status = CatalogAgent["status"];

const STATUS_VARIANT: Record<Status, "default" | "secondary" | "success" | "warning" | "destructive"> = {
  draft: "secondary",
  pending_approval: "warning",
  approved: "secondary",
  published: "success",
  deprecated: "warning",
  archived: "destructive",
};

const COLUMNS: ColumnDef<CatalogAgent>[] = [
  { key: "name", header: "Agent", cell: (a) => <span className="font-medium">{a.name}</span> },
  {
    key: "version",
    header: "Version",
    cell: (a) => <code className="text-xs">{a.current_version}</code>,
  },
  {
    key: "status",
    header: "Status",
    cell: (a) => <Badge variant={STATUS_VARIANT[a.status]}>{a.status.replace("_", " ")}</Badge>,
  },
  { key: "owner", header: "Owner", cell: (a) => a.owner },
  {
    key: "updated",
    header: "Updated",
    cell: (a) => new Date(a.updated_at).toLocaleString(),
  },
];

export default function AgentCatalogPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["enterprise", "catalog", "agents"],
    queryFn: () => adminApi.listCatalogAgents(),
  });

  return (
    <PageShell
      title="Agent Catalog"
      description="Versioned agents with their current lifecycle status (draft → published → deprecated → archived)."
    >
      <SectionCard>
        <DataTable
          columns={COLUMNS}
          rows={data?.items}
          isLoading={isLoading}
          rowKey={(a) => a.id}
          emptyState="No catalog entries yet."
        />
      </SectionCard>
    </PageShell>
  );
}
