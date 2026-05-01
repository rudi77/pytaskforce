import { useMemo, useState } from "react";
import { Search, Sparkles } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ToolSchemaView } from "@/features/tools/ToolSchemaView";
import {
  useTools,
  useSkills,
  useSkill,
  type ToolEntry,
  type SkillSummary,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import {
  CAPABILITY_GROUPS,
  groupForSkill,
  groupForTool,
  labelForTool,
  isHighRiskTool,
  type CapabilityGroupId,
} from "@/features/capabilities/capability-groups";
import { cn } from "@/lib/utils";

type SelectionKind = "tool" | "skill";

interface Selection {
  kind: SelectionKind;
  name: string;
}

interface CapabilityRow {
  kind: SelectionKind;
  name: string;
  label: string;
  description: string;
  group: CapabilityGroupId;
  meta?: {
    needsApproval?: boolean;
    riskLevel?: string;
    skillType?: string;
    slashName?: string | null;
  };
}

function toolRow(tool: ToolEntry): CapabilityRow {
  return {
    kind: "tool",
    name: tool.name,
    label: labelForTool(tool.name),
    description: tool.description ?? "",
    group: groupForTool(tool.name),
    meta: {
      needsApproval: !!tool.requires_approval,
      riskLevel: tool.approval_risk_level,
    },
  };
}

function skillRow(skill: SkillSummary): CapabilityRow {
  return {
    kind: "skill",
    name: skill.name,
    label: skill.slash_name ? `/${skill.slash_name}` : skill.name,
    description: skill.description,
    group: groupForSkill(skill.name, skill.skill_type),
    meta: {
      skillType: skill.skill_type,
      slashName: skill.slash_name,
    },
  };
}

function GroupHeading({
  group,
  count,
}: {
  group: (typeof CAPABILITY_GROUPS)[number];
  count: number;
}) {
  const Icon = group.icon;
  return (
    <div className="flex items-start gap-3 px-1 pt-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div className="flex-1">
        <p className="text-sm font-semibold">{group.label}</p>
        <p className="text-xs text-muted-foreground">{group.description}</p>
      </div>
      <Badge variant="outline" className="font-mono text-[10px]">
        {count}
      </Badge>
    </div>
  );
}

function CapabilityRowItem({
  row,
  active,
  onSelect,
}: {
  row: CapabilityRow;
  active: boolean;
  onSelect: () => void;
}) {
  const high = row.kind === "tool" && isHighRiskTool(row.name);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-md border border-transparent px-3 py-2 text-left transition-colors",
        active
          ? "border-primary/40 bg-primary/10"
          : "hover:bg-accent",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-medium">{row.label}</p>
        <div className="flex shrink-0 gap-1">
          {row.kind === "skill" ? (
            <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
              Workflow
            </Badge>
          ) : null}
          {high ? (
            <Badge variant="warning" className="px-1.5 py-0 text-[10px]">
              Erweitert
            </Badge>
          ) : null}
          {row.kind === "tool" && row.meta?.needsApproval ? (
            <Badge variant="warning" className="px-1.5 py-0 text-[10px]">
              Genehmigung
            </Badge>
          ) : null}
        </div>
      </div>
      {row.description ? (
        <p className="line-clamp-2 text-xs text-muted-foreground">
          {row.description}
        </p>
      ) : null}
      <p className="mt-0.5 font-mono text-[10px] text-muted-foreground/70">
        {row.name}
      </p>
    </button>
  );
}

function ToolDetail({ tool }: { tool: ToolEntry }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline">Werkzeug</Badge>
        {tool.requires_approval ? (
          <Badge variant="warning">Braucht Genehmigung</Badge>
        ) : (
          <Badge variant="secondary">Läuft automatisch</Badge>
        )}
        {tool.approval_risk_level ? (
          <Badge variant="outline">Risiko: {tool.approval_risk_level}</Badge>
        ) : null}
        {isHighRiskTool(tool.name) ? (
          <Badge variant="warning">Erweitert</Badge>
        ) : null}
      </div>
      {tool.description ? (
        <p className="text-sm text-muted-foreground">{tool.description}</p>
      ) : null}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Parameter
        </p>
        <ToolSchemaView schema={tool.parameters_schema} />
      </div>
    </div>
  );
}

function SkillDetailView({ skillName }: { skillName: string }) {
  const { data, isLoading } = useSkill(skillName);
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-4 w-full" />
        ))}
      </div>
    );
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground">Konnte Skill nicht laden.</p>;
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="secondary">Workflow</Badge>
        <Badge variant="outline">Typ: {data.skill_type}</Badge>
        {data.slash_name ? (
          <Badge variant="outline" className="font-mono text-[10px]">
            /{data.slash_name}
          </Badge>
        ) : null}
      </div>
      {data.description ? (
        <p className="text-sm text-muted-foreground">{data.description}</p>
      ) : null}
      <div className="rounded-md border border-border bg-muted/30 p-3 text-xs">
        <pre className="whitespace-pre-wrap font-mono leading-relaxed">
          {data.body || "(keine Beschreibung in SKILL.md)"}
        </pre>
      </div>
    </div>
  );
}

export default function CapabilitiesPage() {
  const tools = useTools();
  const skills = useSkills();
  const [search, setSearch] = useState("");
  const [activeGroup, setActiveGroup] = useState<CapabilityGroupId | "all">("all");
  const [selection, setSelection] = useState<Selection | null>(null);

  const rows = useMemo<CapabilityRow[]>(() => {
    const all: CapabilityRow[] = [];
    for (const tool of tools.data?.tools ?? []) all.push(toolRow(tool));
    for (const skill of skills.data?.skills ?? []) all.push(skillRow(skill));
    return all;
  }, [tools.data, skills.data]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (activeGroup !== "all" && row.group !== activeGroup) return false;
      if (!needle) return true;
      return [row.name, row.label, row.description].join(" ").toLowerCase().includes(needle);
    });
  }, [rows, search, activeGroup]);

  const grouped = useMemo(() => {
    const out = new Map<CapabilityGroupId, CapabilityRow[]>();
    for (const group of CAPABILITY_GROUPS) out.set(group.id, []);
    for (const row of filtered) {
      const arr = out.get(row.group);
      if (arr) arr.push(row);
    }
    for (const arr of out.values()) {
      arr.sort((a, b) => a.label.localeCompare(b.label));
    }
    return out;
  }, [filtered]);

  const selectedTool = useMemo(
    () =>
      selection?.kind === "tool"
        ? (tools.data?.tools ?? []).find((t) => t.name === selection.name) ?? null
        : null,
    [selection, tools.data],
  );

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: rows.length };
    for (const group of CAPABILITY_GROUPS) {
      c[group.id] = rows.filter((r) => r.group === group.id).length;
    }
    return c;
  }, [rows]);

  const isLoading = tools.isLoading || skills.isLoading;
  const error = tools.error || skills.error;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
      <Card className="lg:max-h-[calc(100vh-12rem)] lg:overflow-hidden">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Fähigkeiten
          </CardTitle>
          <CardDescription>
            Alles, was deine Agenten können — Werkzeuge, Workflows und Verbindungen
            an einem Ort. Klick auf eine Fähigkeit für Details.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex h-full min-h-0 flex-col gap-3 pt-0">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Suchen…"
              className="pl-8"
            />
          </div>

          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              onClick={() => setActiveGroup("all")}
              className={cn(
                "rounded-md border px-2 py-1 text-xs",
                activeGroup === "all"
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-accent",
              )}
            >
              Alle ({counts.all ?? 0})
            </button>
            {CAPABILITY_GROUPS.map((group) => {
              const n = counts[group.id] ?? 0;
              if (n === 0) return null;
              return (
                <button
                  key={group.id}
                  type="button"
                  onClick={() => setActiveGroup(group.id)}
                  className={cn(
                    "rounded-md border px-2 py-1 text-xs",
                    activeGroup === group.id
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:bg-accent",
                  )}
                >
                  {group.label} ({n})
                </button>
              );
            })}
          </div>

          <div className="min-h-0 flex-1 overflow-auto scrollbar-thin">
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : error ? (
              <EmptyState
                title="Konnte Fähigkeiten nicht laden"
                description={error instanceof ApiError ? error.message : "Backend-Fehler."}
              />
            ) : filtered.length === 0 ? (
              <EmptyState
                title="Keine Treffer"
                description={search ? "Probier einen anderen Suchbegriff." : "Es sind keine Fähigkeiten registriert."}
              />
            ) : (
              <div className="space-y-3 pb-3">
                {CAPABILITY_GROUPS.map((group) => {
                  const items = grouped.get(group.id) ?? [];
                  if (items.length === 0) return null;
                  if (activeGroup !== "all" && activeGroup !== group.id) return null;
                  return (
                    <section key={group.id} className="space-y-1">
                      <GroupHeading group={group} count={items.length} />
                      <ul className="space-y-1">
                        {items.map((row) => (
                          <li key={`${row.kind}:${row.name}`}>
                            <CapabilityRowItem
                              row={row}
                              active={
                                selection?.kind === row.kind &&
                                selection.name === row.name
                              }
                              onSelect={() =>
                                setSelection({ kind: row.kind, name: row.name })
                              }
                            />
                          </li>
                        ))}
                      </ul>
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            {selection ? (selection.kind === "tool" ? selectedTool?.name : selection.name) : "Wähle eine Fähigkeit"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {!selection ? (
            <EmptyState
              title="Nichts ausgewählt"
              description="Klicke links auf eine Fähigkeit, um Details und Parameter zu sehen."
            />
          ) : selection.kind === "tool" ? (
            selectedTool ? (
              <ToolDetail tool={selectedTool} />
            ) : (
              <p className="text-sm text-muted-foreground">Werkzeug nicht gefunden.</p>
            )
          ) : (
            <SkillDetailView skillName={selection.name} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
