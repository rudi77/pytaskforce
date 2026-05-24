import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BranchCompare20Regular, Search20Regular } from "@fluentui/react-icons";
import { Badge, Button, Input } from "@fluentui/react-components";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { AgentSourceBadge } from "@/components/AgentSourceBadge";
import { useActiveDeployment, useAgents, type DeploymentStatus } from "@/api/queries";
import {
  getAgentDescription,
  getAgentId,
  getAgentName,
} from "@/features/agents/agent-helpers";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import { useCurrentPermissions } from "@/lib/permissions";

type SourceFilter = "all" | "profile" | "custom" | "plugin";

const FILTERS: { id: SourceFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "profile", label: "Profile" },
  { id: "custom", label: "Custom" },
  { id: "plugin", label: "Plugin" },
];

/**
 * Maps the legacy shadcn-Badge deployment-status variants to Fluent's
 * `color` axis. Keeps the meaning ("deployed" → green, "failed" → red,
 * "validating/rolled_back" → amber, "pending" → neutral grey).
 */
const STATUS_COLOR: Record<DeploymentStatus, "success" | "warning" | "danger" | "subtle"> = {
  pending: "subtle",
  validating: "warning",
  deployed: "success",
  failed: "danger",
  rolled_back: "warning",
};

function CustomAgentDeploymentBadge({ agentId }: { agentId: string }) {
  const active = useActiveDeployment(agentId);

  if (active.isLoading) {
    return <Badge appearance="tint" color="subtle">Deployment...</Badge>;
  }
  if (!active.data) {
    return <Badge color="warning">Not deployed</Badge>;
  }
  return (
    <Badge color={STATUS_COLOR[active.data.status]}>
      {active.data.environment}: {active.data.status}
    </Badge>
  );
}

export default function AgentsListPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useAgents();
  const permissions = useCurrentPermissions();
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [search, setSearch] = useState("");
  const canCreateAgent = permissions.can("agent:create");

  const items = useMemo(() => {
    if (!data) return [];
    const needle = search.trim().toLowerCase();
    return data.agents.filter((agent) => {
      if (filter !== "all" && agent.source !== filter) return false;
      if (!needle) return true;
      const haystack = [getAgentId(agent), getAgentName(agent), getAgentDescription(agent)]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [data, filter, search]);

  const counts = useMemo(() => {
    const result: Record<SourceFilter, number> = { all: 0, profile: 0, custom: 0, plugin: 0 };
    if (data) {
      result.all = data.agents.length;
      for (const agent of data.agents) result[agent.source] += 1;
    }
    return result;
  }, [data]);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Agents</CardTitle>
            <p className="text-sm text-muted-foreground">
              Custom agents, framework profiles and plugin agents discovered at runtime.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Fluent Button can't host React Router <Link> via asChild —
             *  onClick + navigate keeps SPA routing (loses right-click
             *  open-in-new-tab, accepted for internal nav). */}
            <Button
              appearance="outline"
              icon={<BranchCompare20Regular />}
              onClick={() => navigate("/agents/compare")}
            >
              Compare
            </Button>
            {canCreateAgent ? (
              <>
                <Button
                  appearance="outline"
                  size="small"
                  onClick={() => navigate("/agents/new?advanced=1")}
                  title="Advanced editor with all tabs"
                >
                  Advanced Editor
                </Button>
                <Button
                  appearance="primary"
                  onClick={() => navigate("/agents/new")}
                >
                  + New Agent
                </Button>
              </>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="flex flex-wrap gap-1 rounded-md bg-muted p-1">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    "rounded px-3 py-1 text-xs font-medium transition-colors",
                    filter === f.id
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f.label}
                  <span className="ml-2 text-[10px] tabular-nums opacity-60">
                    {counts[f.id]}
                  </span>
                </button>
              ))}
            </div>
            <div className="flex-1">
              {/* Fluent Input has a built-in `contentBefore` slot — cleaner
               *  than the absolute-positioned search icon shadcn used. */}
              <Input
                contentBefore={<Search20Regular />}
                value={search}
                onChange={(_, data) => setSearch(data.value)}
                placeholder="Search agents…"
                className="w-full"
              />
            </div>
          </div>

          {isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          ) : error ? (
            <EmptyState
              title="Could not load agents"
              description={
                error instanceof ApiError ? error.message : "Backend returned an error."
              }
            />
          ) : items.length === 0 ? (
            <EmptyState
              title="No matching agents"
              description={
                search
                  ? "Try a different search term."
                  : "Install an agent package or create a custom agent to get started."
              }
            />
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {items.map((agent) => {
                const id = getAgentId(agent);
                return (
                  <li key={`${agent.source}:${id}`}>
                    <Link
                      to={`/agents/${encodeURIComponent(id)}`}
                      className="block h-full rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/50"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">
                            {getAgentName(agent)}
                          </p>
                          <p className="truncate text-xs text-muted-foreground">{id}</p>
                        </div>
                        <AgentSourceBadge source={agent.source} />
                      </div>
                      <div className="mt-3">
                        {agent.source === "custom" ? (
                          <CustomAgentDeploymentBadge agentId={agent.agent_id} />
                        ) : (
                          <Badge appearance="outline" color="subtle">
                            {agent.source === "profile" ? "Profile runtime" : "Plugin runtime"}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">
                        {getAgentDescription(agent) || "No description available."}
                      </p>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
