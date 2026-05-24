import { useMemo, useState } from "react";
import { Search20Regular, Sparkle16Regular } from "@fluentui/react-icons";
import { Badge, Input } from "@fluentui/react-components";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  type CapabilityGroup,
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

function GroupSection({
  group,
  rows,
  selection,
  onSelect,
}: {
  group: CapabilityGroup;
  rows: CapabilityRow[];
  selection: Selection | null;
  onSelect: (s: Selection) => void;
}) {
  if (rows.length === 0) return null;
  const Icon = group.icon;
  return (
    <section className="space-y-3">
      <header className="flex items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-tight">{group.label}</h3>
          <p className="truncate text-xs text-muted-foreground">{group.description}</p>
        </div>
        <Badge appearance="outline" color="subtle" className="font-mono text-[10px]">
          {rows.length}
        </Badge>
      </header>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3">
        {rows.map((row) => (
          <CapabilityTile
            key={`${row.kind}:${row.name}`}
            row={row}
            active={selection?.kind === row.kind && selection.name === row.name}
            onSelect={() => onSelect({ kind: row.kind, name: row.name })}
          />
        ))}
      </div>
    </section>
  );
}

function CapabilityTile({
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
        "group flex h-full flex-col gap-2 rounded-xl border bg-card p-4 text-left shadow-sm transition-all",
        "hover:-translate-y-px hover:border-primary/40 hover:shadow-md",
        active
          ? "border-primary/60 ring-2 ring-primary/30"
          : "border-border",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="line-clamp-1 font-medium">{row.label}</p>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {row.kind === "skill" ? (
            <Badge appearance="tint" color="subtle" className="px-1.5 py-0 text-[10px]">
              Workflow
            </Badge>
          ) : (
            <Badge appearance="outline" color="subtle" className="px-1.5 py-0 text-[10px]">
              Werkzeug
            </Badge>
          )}
          {high ? (
            <Badge color="warning" className="px-1.5 py-0 text-[10px]">
              Erweitert
            </Badge>
          ) : null}
          {row.kind === "tool" && row.meta?.needsApproval ? (
            <Badge color="warning" className="px-1.5 py-0 text-[10px]">
              Genehmigung
            </Badge>
          ) : null}
        </div>
      </div>
      {row.description ? (
        <p className="line-clamp-2 text-sm text-muted-foreground">{row.description}</p>
      ) : (
        <p className="line-clamp-2 text-sm italic text-muted-foreground/70">
          Keine Beschreibung verfügbar.
        </p>
      )}
      <p className="mt-auto truncate font-mono text-[11px] text-muted-foreground/70">
        {row.name}
      </p>
    </button>
  );
}

function ToolDetail({ tool }: { tool: ToolEntry }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge appearance="outline" color="subtle">Werkzeug</Badge>
        {tool.requires_approval ? (
          <Badge color="warning">Braucht Genehmigung</Badge>
        ) : (
          <Badge appearance="tint" color="subtle">Läuft automatisch</Badge>
        )}
        {tool.approval_risk_level ? (
          <Badge appearance="outline" color="subtle">Risiko: {tool.approval_risk_level}</Badge>
        ) : null}
        {isHighRiskTool(tool.name) ? <Badge color="warning">Erweitert</Badge> : null}
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
        <Badge appearance="tint" color="subtle">Workflow</Badge>
        <Badge appearance="outline" color="subtle">Typ: {data.skill_type}</Badge>
        {data.slash_name ? (
          <Badge appearance="outline" color="subtle" className="font-mono text-[10px]">
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
    <div className="space-y-5">
      {/* Page header */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2 text-primary">
          <Sparkle16Regular />
          <span className="text-xs font-semibold uppercase tracking-wider">
            Capabilities
          </span>
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">What your agents can do</h2>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Tools, workflows and connections — grouped by task. Click a tile to see
          parameters and details.
        </p>
      </div>

      {/* Toolbar: search + filter chips */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Input
          contentBefore={<Search20Regular />}
          value={search}
          onChange={(_, data) => setSearch(data.value)}
          placeholder="Search capabilities, tools or workflows…"
          className="w-full max-w-md"
        />
        <div className="flex flex-wrap gap-1.5">
          <FilterChip
            active={activeGroup === "all"}
            count={counts.all ?? 0}
            label="Alle"
            onClick={() => setActiveGroup("all")}
          />
          {CAPABILITY_GROUPS.map((group) => {
            const n = counts[group.id] ?? 0;
            if (n === 0) return null;
            return (
              <FilterChip
                key={group.id}
                active={activeGroup === group.id}
                count={n}
                label={group.label}
                onClick={() => setActiveGroup(group.id)}
              />
            );
          })}
        </div>
      </div>

      {/* Two columns: grid + detail */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(360px,420px)]">
        <div className="min-w-0 space-y-6">
          {isLoading ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-28 w-full rounded-xl" />
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
              description={
                search
                  ? "Probier einen anderen Suchbegriff."
                  : "Es sind keine Fähigkeiten registriert."
              }
            />
          ) : (
            CAPABILITY_GROUPS.map((group) => {
              const items = grouped.get(group.id) ?? [];
              if (activeGroup !== "all" && activeGroup !== group.id) return null;
              return (
                <GroupSection
                  key={group.id}
                  group={group}
                  rows={items}
                  selection={selection}
                  onSelect={setSelection}
                />
              );
            })
          )}
        </div>

        <div className="xl:sticky xl:top-4 xl:self-start">
          <Card>
            <CardHeader>
              <CardTitle>
                {selection
                  ? selection.kind === "tool"
                    ? selectedTool?.name ?? selection.name
                    : selection.name
                  : "Wähle eine Fähigkeit"}
              </CardTitle>
              {!selection ? (
                <CardDescription>
                  Details, Parameter und Genehmigungs­anforderungen erscheinen hier.
                </CardDescription>
              ) : null}
            </CardHeader>
            <CardContent className="space-y-5">
              {!selection ? (
                <EmptyState
                  title="Nichts ausgewählt"
                  description="Klick auf eine Kachel — links — um die Details zu öffnen."
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
      </div>
    </div>
  );
}

function FilterChip({
  active,
  count,
  label,
  onClick,
}: {
  active: boolean;
  count: number;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-border bg-card text-muted-foreground hover:bg-accent hover:text-accent-foreground",
      )}
    >
      <span>{label}</span>
      <span
        className={cn(
          "rounded-full px-1.5 py-0.5 font-mono text-[10px]",
          active ? "bg-primary/20" : "bg-muted",
        )}
      >
        {count}
      </span>
    </button>
  );
}
