import { useQuery } from "@tanstack/react-query";
import { Badge } from "@taskforce/ui-shell";

import { adminApi, type AuditEntry } from "../api/admin";
import { DataTable, type ColumnDef } from "../components/DataTable";
import { PageShell, SectionCard } from "../components/PageShell";

const COLUMNS: ColumnDef<AuditEntry>[] = [
  {
    key: "timestamp",
    header: "When",
    cell: (e) => (
      <span className="whitespace-nowrap text-muted-foreground">
        {new Date(e.timestamp).toLocaleString()}
      </span>
    ),
  },
  { key: "actor", header: "Actor", cell: (e) => <span className="font-medium">{e.actor}</span> },
  { key: "action", header: "Action", cell: (e) => e.action },
  { key: "resource", header: "Resource", cell: (e) => <code className="text-xs">{e.resource}</code> },
  {
    key: "outcome",
    header: "Outcome",
    cell: (e) => (
      <Badge variant={e.outcome === "success" ? "success" : "destructive"}>
        {e.outcome}
      </Badge>
    ),
  },
];

export default function AuditLogPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["enterprise", "audit"],
    queryFn: () => adminApi.listAuditEntries(),
    refetchInterval: 30_000,
  });

  return (
    <PageShell
      title="Audit Log"
      description="Compliance-grade trail of every governed action. Retained per the configured policy."
    >
      <SectionCard>
        <DataTable
          columns={COLUMNS}
          rows={data?.items}
          isLoading={isLoading}
          rowKey={(e) => e.id}
          emptyState="No audit entries recorded yet."
        />
      </SectionCard>
    </PageShell>
  );
}
