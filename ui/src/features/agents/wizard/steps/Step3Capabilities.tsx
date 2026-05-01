import { useMemo } from "react";

import { useTools } from "@/api/queries";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import {
  CAPABILITY_GROUPS,
  groupForTool,
  isHighRiskTool,
  labelForTool,
  type CapabilityGroupId,
} from "@/features/capabilities/capability-groups";
import { cn } from "@/lib/utils";
import type { WizardState } from "@/features/agents/wizard/types";

interface Props {
  state: WizardState;
  onChange: (patch: Partial<WizardState>) => void;
}

interface ToolItem {
  name: string;
  label: string;
  description: string;
  group: CapabilityGroupId;
  needsApproval: boolean;
  highRisk: boolean;
}

export function Step3Capabilities({ state, onChange }: Props) {
  const tools = useTools();

  const items = useMemo<ToolItem[]>(() => {
    return (tools.data?.tools ?? []).map((tool) => ({
      name: tool.name,
      label: labelForTool(tool.name),
      description: tool.description ?? "",
      group: groupForTool(tool.name),
      needsApproval: !!tool.requires_approval,
      highRisk: isHighRiskTool(tool.name),
    }));
  }, [tools.data]);

  const grouped = useMemo(() => {
    const out = new Map<CapabilityGroupId, ToolItem[]>();
    for (const group of CAPABILITY_GROUPS) out.set(group.id, []);
    for (const item of items) {
      const arr = out.get(item.group);
      if (arr) arr.push(item);
    }
    for (const arr of out.values()) {
      arr.sort((a, b) => a.label.localeCompare(b.label));
    }
    return out;
  }, [items]);

  const isLoading = tools.isLoading;
  const error = tools.error;

  function toggleTool(name: string) {
    const set = new Set(state.tools);
    if (set.has(name)) set.delete(name);
    else set.add(name);
    onChange({ tools: Array.from(set) });
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <EmptyState
        title="Konnte Fähigkeiten nicht laden"
        description="Backend-Fehler — schließe diesen Wizard und versuche es erneut."
      />
    );
  }

  const selectedTools = new Set(state.tools);
  const recommendedSkills = state.template?.recommended_skills ?? [];

  return (
    <div className="space-y-5">
      <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
        <p className="font-medium">
          Wir haben anhand deiner Vorlage <strong>{selectedTools.size}</strong>{" "}
          Werkzeuge vorausgewählt.
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Du kannst weitere hinzufügen oder welche entfernen — was du nicht brauchst,
          lässt du einfach weg. Auf der Seite „Fähigkeiten“ kannst du alles im Detail nachschlagen.
        </p>
      </div>

      {CAPABILITY_GROUPS.map((group) => {
        const groupItems = grouped.get(group.id) ?? [];
        if (groupItems.length === 0) return null;
        const Icon = group.icon;
        const groupSelected = groupItems.filter((i) => selectedTools.has(i.name)).length;
        return (
          <Card key={group.id}>
            <CardContent className="space-y-2 p-4">
              <div className="flex items-start gap-3">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div className="flex-1">
                  <p className="text-sm font-semibold">{group.label}</p>
                  <p className="text-xs text-muted-foreground">{group.description}</p>
                </div>
                {groupSelected > 0 ? (
                  <Badge variant="secondary" className="shrink-0">
                    {groupSelected}/{groupItems.length}
                  </Badge>
                ) : null}
              </div>
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {groupItems.map((item) => {
                  const checked = selectedTools.has(item.name);
                  return (
                    <li key={item.name}>
                      <label
                        className={cn(
                          "flex cursor-pointer items-start gap-2 rounded-md border px-2.5 py-2 transition-colors",
                          checked
                            ? "border-primary bg-primary/5"
                            : "border-border hover:bg-accent",
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleTool(item.name)}
                          className="mt-0.5"
                        />
                        <span className="flex-1">
                          <span className="flex items-center gap-1.5">
                            <span className="text-sm font-medium">
                              {item.label}
                            </span>
                            {item.highRisk ? (
                              <Badge
                                variant="warning"
                                className="px-1.5 py-0 text-[10px]"
                              >
                                Erweitert
                              </Badge>
                            ) : null}
                            {item.needsApproval ? (
                              <Badge
                                variant="outline"
                                className="px-1.5 py-0 text-[10px]"
                              >
                                Genehmigung
                              </Badge>
                            ) : null}
                          </span>
                          {item.description ? (
                            <span className="block text-xs text-muted-foreground">
                              {item.description}
                            </span>
                          ) : null}
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>
        );
      })}

      {recommendedSkills.length > 0 ? (
        <Card>
          <CardContent className="space-y-2 p-4">
            <p className="text-sm font-semibold">Empfohlene Workflows</p>
            <p className="text-xs text-muted-foreground">
              Diese Skills passen zu deiner Vorlage und stehen dem Agenten
              automatisch zur Verfügung. Du musst sie nicht extra aktivieren —
              der Agent ruft sie bei Bedarf selbst auf oder du startest sie im
              Chat per Slash-Befehl (z.B. <code className="rounded bg-muted px-1">/{recommendedSkills[0]}</code>).
            </p>
            <div className="flex flex-wrap gap-1.5">
              {recommendedSkills.map((skill) => (
                <Badge key={skill} variant="outline">
                  /{skill}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
