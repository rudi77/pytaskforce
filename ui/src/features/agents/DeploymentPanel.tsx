/**
 * DeploymentPanel
 * ----------------
 *
 * Custom-agent deployment widget. Shows the active deployment record for
 * the chosen environment, exposes a "Deploy" button that runs the backend
 * preflight + activation, and renders the rolling deployment history with
 * one-click rollback.
 */
import { useState } from "react";
import { CheckCircle2, History, RefreshCw, Rocket, ShieldAlert, Undo2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/api/client";
import {
  AgentDeployment,
  DeploymentEnvironment,
  DeploymentStatus,
  useActiveDeployment,
  useDeployAgent,
  useDeploymentHistory,
  useRollbackAgent,
} from "@/api/queries";

interface Props {
  agentId: string;
  environment?: DeploymentEnvironment;
}

const STATUS_VARIANT: Record<DeploymentStatus, "success" | "warning" | "destructive" | "secondary"> = {
  pending: "secondary",
  validating: "warning",
  deployed: "success",
  failed: "destructive",
  rolled_back: "warning",
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function StatusBadge({ status }: { status: DeploymentStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>;
}

function ActiveDeploymentSummary({ deployment }: { deployment: AgentDeployment }) {
  return (
    <div className="space-y-1.5 text-sm">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 text-success" />
        <span className="font-medium">Active version:</span>
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{deployment.version}</code>
        <StatusBadge status={deployment.status} />
      </div>
      <p className="text-xs text-muted-foreground">
        Deployed {formatDateTime(deployment.deployed_at)}
        {deployment.deployed_by ? ` by ${deployment.deployed_by}` : ""}
      </p>
      {deployment.message ? (
        <p className="text-xs italic text-muted-foreground">"{deployment.message}"</p>
      ) : null}
    </div>
  );
}

function NoActiveDeployment() {
  return (
    <div className="flex items-start gap-2 rounded-md border border-dashed border-warning/40 bg-warning/5 p-3 text-sm">
      <ShieldAlert className="mt-0.5 h-4 w-4 text-warning" />
      <div>
        <p className="font-medium">Not deployed yet.</p>
        <p className="text-xs text-muted-foreground">
          Custom agents must be deployed before they can be invoked via{" "}
          <code className="rounded bg-muted px-1 py-0.5">POST /api/v1/execute</code>.
        </p>
      </div>
    </div>
  );
}

export function DeploymentPanel({ agentId, environment = "local" }: Props) {
  const active = useActiveDeployment(agentId, environment);
  const history = useDeploymentHistory(agentId);
  const deployMutation = useDeployAgent(agentId);
  const rollbackMutation = useRollbackAgent(agentId);
  const [error, setError] = useState<string | null>(null);

  const isBusy = deployMutation.isPending || rollbackMutation.isPending;

  const onDeploy = async () => {
    setError(null);
    try {
      await deployMutation.mutateAsync({ environment });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  const onRollback = async (toVersion: string) => {
    setError(null);
    try {
      await rollbackMutation.mutateAsync({ to_version: toVersion, environment });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  return (
    <Card data-testid="deployment-panel">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Rocket className="h-4 w-4" />
              Deployment
            </CardTitle>
            <CardDescription>
              Activate this custom agent for the <strong>{environment}</strong> environment.
              Preflight checks run automatically before activation.
            </CardDescription>
          </div>
          <Button onClick={onDeploy} disabled={isBusy} size="sm" data-testid="deploy-button">
            {deployMutation.isPending ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Rocket className="h-4 w-4" />
            )}
            Deploy
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {active.isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : active.data ? (
          <ActiveDeploymentSummary deployment={active.data} />
        ) : (
          <NoActiveDeployment />
        )}

        <section className="space-y-2">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <History className="h-3.5 w-3.5" />
            History
          </p>
          {history.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : !history.data || history.data.deployments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No deployments recorded yet.</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {history.data.deployments.map((d, idx) => (
                <li
                  key={`${d.version}-${idx}`}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                >
                  <div className="min-w-0 space-y-0.5">
                    <div className="flex items-center gap-2">
                      <code className="truncate rounded bg-muted px-1.5 py-0.5 text-xs">
                        {d.version}
                      </code>
                      <StatusBadge status={d.status} />
                      <span className="text-xs text-muted-foreground">{d.environment}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(d.deployed_at)}
                      {d.deployed_by ? ` · ${d.deployed_by}` : ""}
                      {d.error ? ` · ${d.error}` : ""}
                    </p>
                  </div>
                  {d.status === "deployed" &&
                  active.data &&
                  d.version !== active.data.version ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => onRollback(d.version)}
                      disabled={isBusy}
                    >
                      <Undo2 className="h-3.5 w-3.5" />
                      Roll back
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
