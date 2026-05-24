import { useEffect, useMemo, useState } from "react";
import { Button } from "@fluentui/react-components";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useSettingsSection,
  useUpdateSettingsSection,
  useDeleteSettingsSection,
  useTools,
} from "@/api/queries";
import ForbiddenNotice, { isForbiddenError } from "@/features/settings/ForbiddenNotice";

interface ApprovalData {
  bypass_tools: string[];
}

const RISK_BADGE_CLASS: Record<string, string> = {
  high: "bg-destructive/15 text-destructive",
  medium: "bg-warning/15 text-warning",
  low: "bg-muted text-muted-foreground",
};

export default function ApprovalsTab() {
  const sectionQuery = useSettingsSection<ApprovalData>("approval");
  const toolsQuery = useTools();
  const update = useUpdateSettingsSection<ApprovalData>();
  const reset = useDeleteSettingsSection();

  const overrideActive = Boolean(sectionQuery.data?.data?.bypass_tools?.length);
  const [draftSet, setDraftSet] = useState<Set<string>>(new Set());

  // Initialize draft from current override; default to empty (no bypass).
  useEffect(() => {
    if (sectionQuery.data?.data?.bypass_tools?.length) {
      setDraftSet(new Set(sectionQuery.data.data.bypass_tools));
    } else if (sectionQuery.data && !sectionQuery.data.data?.bypass_tools?.length) {
      setDraftSet(new Set());
    }
  }, [sectionQuery.data]);

  // Show only tools that actually go through the approval gate. A tool with
  // ``requires_approval: false`` never hits the gate so bypassing it is a
  // no-op — leaving it off the list keeps the choice meaningful.
  const approvalGatedTools = useMemo(() => {
    const all = toolsQuery.data?.tools ?? [];
    return [...all]
      .filter((t) => t.requires_approval === true)
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [toolsQuery.data]);

  // Hooks must come before early returns to keep call order stable.
  if (isForbiddenError(sectionQuery.error)) {
    return <ForbiddenNotice error={sectionQuery.error} area="approval settings" />;
  }

  const toggle = (name: string) => {
    setDraftSet((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const save = () => {
    update.mutate({
      section: "approval",
      data: { bypass_tools: Array.from(draftSet).sort() },
    });
  };

  const resetToDefault = () => {
    reset.mutate("approval");
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Approval bypass</CardTitle>
          <CardDescription>
            Tools whose <code>requires_approval</code> is true normally pause the
            agent and wait for a human grant. Check a tool here to{" "}
            <strong>skip the approval prompt</strong> for it on this tenant — the
            agent runs the call directly. Combines (UNION) with any{" "}
            <code>agent.approval_bypass_tools</code> set in a profile YAML.
            Reserve this for trusted single-user workflows where the gate is
            friction rather than safety.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">
            Override:{" "}
            {overrideActive
              ? `${sectionQuery.data?.data?.bypass_tools?.length ?? 0} tool(s) bypassed`
              : "none (every approval-gated tool prompts)"}
          </span>
          <span className="ml-auto flex gap-2">
            <Button appearance="primary" onClick={save} disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save override"}
            </Button>
            <Button
              appearance="outline"
              onClick={resetToDefault}
              disabled={!overrideActive || reset.isPending}
            >
              Reset
            </Button>
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-1 p-4">
          {toolsQuery.isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : approvalGatedTools.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No approval-gated tools registered.
            </p>
          ) : (
            approvalGatedTools.map((tool) => {
              const risk = tool.approval_risk_level ?? "low";
              return (
                <label
                  key={tool.name}
                  className="flex items-start gap-3 rounded-md p-2 hover:bg-muted/40"
                >
                  {/* Raw <input type="checkbox"> kept — Fluent Checkbox
                   *  has its own onChange (_, data) signature and changes
                   *  the focus model. Separate primitive sweep. */}
                  <input
                    type="checkbox"
                    checked={draftSet.has(tool.name)}
                    onChange={() => toggle(tool.name)}
                    className="mt-1"
                  />
                  <div className="flex-1 space-y-0.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{tool.name}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium uppercase ${
                          RISK_BADGE_CLASS[risk] ?? RISK_BADGE_CLASS.low
                        }`}
                      >
                        {risk}
                      </span>
                    </div>
                    {tool.description ? (
                      <p className="text-xs text-muted-foreground">
                        {tool.description}
                      </p>
                    ) : null}
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
