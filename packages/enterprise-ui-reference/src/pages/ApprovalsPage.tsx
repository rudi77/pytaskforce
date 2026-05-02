import { useQuery } from "@tanstack/react-query";
import { Badge } from "@taskforce/ui-shell";

import { adminApi, type ApprovalRequest } from "../api/admin";
import { DataTable, type ColumnDef } from "../components/DataTable";
import { PageShell, SectionCard } from "../components/PageShell";

type Status = ApprovalRequest["status"];

const STATUS_VARIANT: Record<Status, "default" | "secondary" | "success" | "warning" | "destructive"> = {
  pending: "warning",
  approved: "success",
  rejected: "destructive",
  expired: "secondary",
};

const COLUMNS: ColumnDef<ApprovalRequest>[] = [
  {
    key: "resource",
    header: "Resource",
    cell: (r) => (
      <div>
        <div className="text-xs text-muted-foreground">{r.resource_type}</div>
        <code className="text-xs">{r.resource_id}</code>
      </div>
    ),
  },
  { key: "requested_by", header: "Requested by", cell: (r) => r.requested_by },
  {
    key: "requested_at",
    header: "When",
    cell: (r) => (
      <span className="whitespace-nowrap text-muted-foreground">
        {new Date(r.requested_at).toLocaleString()}
      </span>
    ),
  },
  {
    key: "reviewers",
    header: "Reviewers",
    cell: (r) =>
      r.reviewers.length === 0 ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        r.reviewers.join(", ")
      ),
  },
  {
    key: "status",
    header: "Status",
    cell: (r) => <Badge variant={STATUS_VARIANT[r.status]}>{r.status}</Badge>,
  },
];

export default function ApprovalsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["enterprise", "approvals"],
    queryFn: () => adminApi.listApprovals(),
    refetchInterval: 60_000,
  });

  return (
    <PageShell
      title="Approvals"
      description="Pending and recent approval workflows for governed agent publishing."
    >
      <SectionCard>
        <DataTable
          columns={COLUMNS}
          rows={data?.items}
          isLoading={isLoading}
          rowKey={(r) => r.id}
          emptyState="No approval requests pending."
        />
      </SectionCard>
    </PageShell>
  );
}
