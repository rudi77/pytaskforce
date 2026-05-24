import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft20Regular, Delete20Regular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { AgentSourceBadge } from "@/components/AgentSourceBadge";
import { AgentProfileEditor } from "@/features/agents/AgentProfileEditor";
import { AgentWizard } from "@/features/agents/wizard/AgentWizard";
import { DeploymentPanel } from "@/features/agents/DeploymentPanel";
import { ApiError, apiFetch } from "@/api/client";
import {
  AgentSummary,
  queryKeys,
  useDeleteCustomAgent,
} from "@/api/queries";
import {
  getAgentDescription,
  getAgentName,
  getAgentTools,
} from "@/features/agents/agent-helpers";
import { toast } from "@/components/ui/toast";
import { useCurrentPermissions } from "@/lib/permissions";

interface Props {
  mode: "create" | "edit";
}

function ForbiddenAgentAction() {
  const navigate = useNavigate();
  return (
    <EmptyState
      title="Forbidden"
      description="Your account can use agents, but it cannot create or modify them."
      action={
        <Button variant="outline" onClick={() => navigate("/agents")}>
          Back to agents
        </Button>
      }
    />
  );
}

function useAgent(agentId: string | undefined) {
  return useQuery<AgentSummary>({
    queryKey: queryKeys.agent(agentId ?? ""),
    queryFn: () => apiFetch<AgentSummary>(`/api/v1/agents/${encodeURIComponent(agentId!)}`),
    enabled: !!agentId,
    retry: false,
  });
}

function CustomOrPluginDetail({ agent }: { agent: AgentSummary }) {
  if (agent.source === "profile") return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuration</CardTitle>
        <CardDescription>
          Custom and plugin agents are managed via the legacy ``/api/v1/agents``
          endpoint. The full editor lands together with the legacy-CRUD wiring.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {agent.source === "custom" ? (
          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              System prompt
            </p>
            <pre className="max-h-72 overflow-auto scrollbar-thin whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-3 text-xs">
              {agent.system_prompt}
            </pre>
          </div>
        ) : null}
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Tools
          </p>
          {getAgentTools(agent).length === 0 ? (
            <p className="text-sm text-muted-foreground">None.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {getAgentTools(agent).map((t) => (
                <Badge key={t} variant="outline">
                  {t}
                </Badge>
              ))}
            </div>
          )}
        </div>
        {agent.mcp_servers.length > 0 ? (
          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              MCP servers
            </p>
            <pre className="overflow-auto scrollbar-thin rounded-md border border-border bg-muted/40 p-3 text-xs">
              {JSON.stringify(agent.mcp_servers, null, 2)}
            </pre>
          </div>
        ) : null}
        {agent.source === "plugin" ? (
          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Plugin path
            </p>
            <p className="font-mono text-sm text-muted-foreground">{agent.plugin_path}</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CustomOrPluginView({ agent }: { agent: AgentSummary }) {
  const navigate = useNavigate();
  const deleteMutation = useDeleteCustomAgent();
  const permissions = useCurrentPermissions();
  const canDeleteAgent = permissions.can("agent:delete");

  const onDelete = async () => {
    if (agent.source !== "custom") return;
    if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return;
    try {
      await deleteMutation.mutateAsync(agent.agent_id);
      toast.success("Agent deleted", agent.name);
      navigate("/agents");
    } catch (err) {
      toast.error(
        "Delete failed",
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate("/agents")}>
          <ArrowLeft20Regular className="h-4 w-4" />
          All agents
        </Button>
        {agent.source === "custom" && canDeleteAgent ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onDelete}
            disabled={deleteMutation.isPending}
            className="ml-auto"
          >
            <Delete20Regular className="h-4 w-4" />
            Delete
          </Button>
        ) : null}
      </div>
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{getAgentName(agent)}</CardTitle>
              <CardDescription>{getAgentDescription(agent)}</CardDescription>
            </div>
            <AgentSourceBadge source={agent.source} />
          </div>
        </CardHeader>
      </Card>
      {agent.source === "custom" ? <DeploymentPanel agentId={agent.agent_id} /> : null}
      <CustomOrPluginDetail agent={agent} />
    </div>
  );
}

function EditMode({ agentId }: { agentId: string }) {
  const navigate = useNavigate();
  const agentQuery = useAgent(agentId);

  if (agentQuery.isLoading) return <Skeleton className="h-96 w-full" />;
  if (agentQuery.error) {
    const isMissing = agentQuery.error instanceof ApiError && agentQuery.error.status === 404;
    return (
      <EmptyState
        title={isMissing ? "Agent not found" : "Could not load agent"}
        description={
          agentQuery.error instanceof ApiError
            ? agentQuery.error.message
            : "Backend returned an error."
        }
        action={
          <Button variant="outline" onClick={() => navigate("/agents")}>
            Back to agents
          </Button>
        }
      />
    );
  }
  if (!agentQuery.data) return null;

  if (agentQuery.data.source === "profile") {
    return <AgentProfileEditor mode="edit" profileName={agentQuery.data.profile} />;
  }
  return <CustomOrPluginView agent={agentQuery.data} />;
}

export default function AgentEditorPage({ mode }: Props) {
  const { agentId } = useParams();
  const [params] = useSearchParams();
  const advanced = params.get("advanced") === "1";
  const permissions = useCurrentPermissions();

  if (mode === "create") {
    if (permissions.isLoading) return <Skeleton className="h-96 w-full" />;
    if (!permissions.isLoading && !permissions.can("agent:create")) {
      return <ForbiddenAgentAction />;
    }
    return advanced ? <AgentProfileEditor mode="create" /> : <AgentWizard />;
  }
  if (!agentId) {
    if (permissions.isLoading) return <Skeleton className="h-96 w-full" />;
    if (!permissions.can("agent:create")) {
      return <ForbiddenAgentAction />;
    }
    return advanced ? <AgentProfileEditor mode="create" /> : <AgentWizard />;
  }
  return <EditMode agentId={agentId} />;
}
