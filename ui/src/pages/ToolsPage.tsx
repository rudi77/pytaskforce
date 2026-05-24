import { useMemo, useState } from "react";
import {
  Search20Regular,
  ShieldCheckmark20Regular,
  ShieldError20Regular,
} from "@fluentui/react-icons";
import { Badge, Input } from "@fluentui/react-components";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ToolSchemaView } from "@/features/tools/ToolSchemaView";
import { useTools, type ToolEntry } from "@/api/queries";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";

/** Maps legacy shadcn Badge variants to Fluent appearance + color. */
const RISK_DEF: Record<
  string,
  { color: "subtle" | "warning" | "danger"; label: string }
> = {
  low: { color: "subtle", label: "Low risk" },
  medium: { color: "warning", label: "Medium risk" },
  high: { color: "danger", label: "High risk" },
};

function ToolBadges({ tool }: { tool: ToolEntry }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tool.requires_approval ? (
        <Badge color="warning" icon={<ShieldError20Regular />}>
          Needs approval
        </Badge>
      ) : (
        <Badge appearance="outline" color="subtle" icon={<ShieldCheckmark20Regular />}>
          Auto-run
        </Badge>
      )}
      {tool.approval_risk_level
        ? (() => {
            const def = RISK_DEF[tool.approval_risk_level.toLowerCase()];
            return def ? <Badge color={def.color}>{def.label}</Badge> : null;
          })()
        : null}
      {tool.origin ? (
        <Badge appearance="outline" color="subtle" className="font-mono text-[10px]">
          {tool.origin}
        </Badge>
      ) : null}
    </div>
  );
}

export default function ToolsPage() {
  const { data, isLoading, error } = useTools();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const tools = useMemo(() => {
    if (!data) return [];
    const list = [...data.tools].sort((a, b) => a.name.localeCompare(b.name));
    const needle = search.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((t) =>
      [t.name, t.description ?? "", t.origin ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [data, search]);

  const selectedTool = useMemo(
    () => (selected ? tools.find((t) => t.name === selected) ?? null : null),
    [selected, tools],
  );

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
      <Card className="lg:max-h-[calc(100vh-12rem)] lg:overflow-hidden">
        <CardHeader>
          <CardTitle>Tool catalog</CardTitle>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.tools.length} tools registered` : "Loading…"}
          </p>
        </CardHeader>
        <CardContent className="flex h-full min-h-0 flex-col gap-3 pt-0">
          <Input
            contentBefore={<Search20Regular />}
            value={search}
            onChange={(_, data) => setSearch(data.value)}
            placeholder="Search tools…"
          />

          <div className="min-h-0 flex-1 overflow-auto scrollbar-thin">
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : error ? (
              <EmptyState
                title="Could not load tools"
                description={error instanceof ApiError ? error.message : "Backend error."}
              />
            ) : tools.length === 0 ? (
              <EmptyState
                title="No matching tools"
                description={search ? "Try a different search term." : "The registry is empty."}
              />
            ) : (
              <ul className="space-y-1">
                {tools.map((tool) => (
                  <li key={tool.name}>
                    <button
                      type="button"
                      onClick={() => setSelected(tool.name)}
                      className={cn(
                        "w-full rounded-md border border-transparent px-3 py-2 text-left transition-colors",
                        selected === tool.name
                          ? "border-primary/40 bg-primary/10"
                          : "hover:bg-accent",
                      )}
                    >
                      <p className="text-sm font-medium">{tool.name}</p>
                      {tool.description ? (
                        <p className="line-clamp-2 text-xs text-muted-foreground">
                          {tool.description}
                        </p>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{selectedTool?.name ?? "Select a tool"}</CardTitle>
          {selectedTool?.description ? (
            <p className="text-sm text-muted-foreground">{selectedTool.description}</p>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-5">
          {!selectedTool ? (
            <EmptyState
              title="No tool selected"
              description="Pick a tool from the catalog to inspect its parameter schema."
            />
          ) : (
            <>
              <ToolBadges tool={selectedTool} />
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Parameters
                </p>
                <ToolSchemaView schema={selectedTool.parameters_schema} />
              </div>
              {selectedTool.parameters_schema ? (
                <details className="rounded-md border border-border bg-muted/30 p-3 text-xs">
                  <summary className="cursor-pointer font-medium text-muted-foreground">
                    Raw JSON Schema
                  </summary>
                  <pre className="mt-2 overflow-auto scrollbar-thin">
                    {JSON.stringify(selectedTool.parameters_schema, null, 2)}
                  </pre>
                </details>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
