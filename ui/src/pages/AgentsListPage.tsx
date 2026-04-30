import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { GitCompare, Search } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { AgentSourceBadge } from "@/components/AgentSourceBadge";
import { useAgents } from "@/api/queries";
import {
  getAgentDescription,
  getAgentId,
  getAgentName,
} from "@/features/agents/agent-helpers";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";

type SourceFilter = "all" | "profile" | "custom" | "plugin";

const FILTERS: { id: SourceFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "profile", label: "Profile" },
  { id: "custom", label: "Custom" },
  { id: "plugin", label: "Plugin" },
];

export default function AgentsListPage() {
  const { data, isLoading, error } = useAgents();
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [search, setSearch] = useState("");

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
            <Button asChild variant="outline">
              <Link to="/agents/compare">
                <GitCompare className="h-4 w-4" />
                Compare
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/agents/new?advanced=1" title="Profi-Editor mit allen Tabs">
                Profi-Editor
              </Link>
            </Button>
            <Button asChild>
              <Link to="/agents/new">+ Neuer Agent</Link>
            </Button>
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
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search agents…"
                className="pl-8"
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
