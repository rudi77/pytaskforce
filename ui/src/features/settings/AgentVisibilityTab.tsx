import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentSourceBadge } from "@/components/AgentSourceBadge";
import {
  useAllAgentsForVisibility,
  useSettingsSection,
  useUpdateSettingsSection,
  useDeleteSettingsSection,
} from "@/api/queries";
import {
  getAgentDescription,
  getAgentId,
  getAgentName,
} from "@/features/agents/agent-helpers";
import ForbiddenNotice, { isForbiddenError } from "@/features/settings/ForbiddenNotice";

interface VisibilityData {
  agents: string[];
}

export default function AgentVisibilityTab() {
  const allAgents = useAllAgentsForVisibility();
  const sectionQuery = useSettingsSection<VisibilityData>("visible_agents");
  const update = useUpdateSettingsSection<VisibilityData>();
  const reset = useDeleteSettingsSection();

  const overrideActive = Boolean(sectionQuery.data?.data?.agents?.length);
  const [draftSet, setDraftSet] = useState<Set<string>>(new Set());

  // Initialize draft from current override OR (when none) from agents currently
  // visible (those returned by /agents without ?include_hidden=true).
  // Once we have all agents, default-select the ones whose current visibility
  // we observe — that way unticking one and saving creates a precise override.
  useEffect(() => {
    if (sectionQuery.data?.data?.agents?.length) {
      setDraftSet(new Set(sectionQuery.data.data.agents));
    } else if (allAgents.data) {
      // Default state: every agent ticked. Operator can untick to hide.
      setDraftSet(new Set(allAgents.data.agents.map((a) => getAgentId(a))));
    }
  }, [sectionQuery.data, allAgents.data]);

  const sortedAgents = useMemo(() => {
    if (!allAgents.data) return [];
    return [...allAgents.data.agents].sort((a, b) =>
      getAgentName(a).localeCompare(getAgentName(b)),
    );
  }, [allAgents.data]);

  // Early returns must come AFTER every hook is invoked above so the
  // hook-call order stays stable across renders (Rules of Hooks).
  if (isForbiddenError(sectionQuery.error) || isForbiddenError(allAgents.error)) {
    return (
      <ForbiddenNotice
        error={sectionQuery.error ?? allAgents.error}
        area="agent visibility settings"
      />
    );
  }

  const toggle = (id: string) => {
    setDraftSet((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const save = () => {
    update.mutate({
      section: "visible_agents",
      data: { agents: Array.from(draftSet).sort() },
    });
  };

  const resetToYaml = () => {
    reset.mutate("visible_agents");
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Agent Visibility</CardTitle>
          <CardDescription>
            Choose which agents appear in the catalogue. Hidden agents stay loadable by id, so
            master agents can still extend them as sub-agents — they just don't surface in
            <code className="ml-1">/api/v1/agents</code> or the Agents page. When no override is
            active, the shipped <code>deployment.yaml</code> is used.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">
            Override: {overrideActive ? "active (settings)" : "none (using deployment.yaml)"}
          </span>
          <span className="ml-auto flex gap-2">
            <Button onClick={save} disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save override"}
            </Button>
            <Button
              variant="outline"
              onClick={resetToYaml}
              disabled={!overrideActive || reset.isPending}
            >
              Reset to default
            </Button>
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-1 p-4">
          {allAgents.isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            sortedAgents.map((agent) => {
              const id = getAgentId(agent);
              return (
                <label
                  key={id}
                  className="flex items-start gap-3 rounded-md p-2 hover:bg-muted/40"
                >
                  <input
                    type="checkbox"
                    checked={draftSet.has(id)}
                    onChange={() => toggle(id)}
                    className="mt-1"
                  />
                  <div className="flex-1 space-y-0.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{getAgentName(agent)}</span>
                      <AgentSourceBadge source={agent.source} />
                      <span className="text-xs text-muted-foreground">{id}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {getAgentDescription(agent)}
                    </p>
                  </div>
                </label>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
