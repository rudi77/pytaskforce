import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, List } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import {
  useSaveWorkflowDefinition,
  useWorkflowDefinition,
  type WorkflowStep,
} from "@/api/queries";
import { WorkflowGraph } from "@/features/workflows/graph/WorkflowGraph";
import { WorkflowEditor } from "@/features/workflows/WorkflowEditor";
import { toast } from "@/components/ui/toast";

/**
 * Visual workflow graph page. Renders the selected workflow as a
 * top-down DAG; clicking a step opens the existing form-based
 * {@link WorkflowEditor} dialog scoped to that step.
 *
 * Sister of {@link WorkflowsPage} — the list / quick-edit path stays
 * unchanged.
 */
export default function WorkflowGraphPage() {
  const { workflowId = "" } = useParams<{ workflowId: string }>();
  const query = useWorkflowDefinition(workflowId);
  const saveMutation = useSaveWorkflowDefinition();
  const [editorOpen, setEditorOpen] = useState(false);

  const workflow = query.data?.workflow ?? null;

  const onStepClick = (_step: WorkflowStep) => {
    // The existing WorkflowEditor edits the whole workflow with all
    // steps in a single dialog; jumping into the dialog selects the
    // step implicitly via the step list. A future iteration could
    // pre-scroll / pre-focus the clicked step.
    setEditorOpen(true);
  };

  const onSubmit = async (payload: typeof workflow) => {
    if (!payload) return;
    try {
      await saveMutation.mutateAsync(payload);
      toast.success("Workflow saved", payload.name || payload.workflow_id);
    } catch (err) {
      toast.error(
        "Save failed",
        err instanceof Error ? err.message : "Unknown error",
      );
      throw err;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Button asChild variant="ghost" size="sm">
          <Link to="/workflows">
            <ArrowLeft className="h-4 w-4" />
            All workflows
          </Link>
        </Button>
        <Button variant="outline" size="sm" onClick={() => setEditorOpen(true)}>
          <List className="h-4 w-4" />
          Edit as list
        </Button>
      </div>

      {query.isLoading ? (
        <Skeleton className="h-[640px] w-full" />
      ) : query.isError ? (
        <Card>
          <CardContent className="p-6">
            <EmptyState
              title="Workflow konnte nicht geladen werden"
              description={
                query.error instanceof ApiError
                  ? query.error.message
                  : "Backend antwortet nicht."
              }
            />
          </CardContent>
        </Card>
      ) : workflow ? (
        <>
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2">
              <div>
                <CardTitle className="flex items-center gap-2">
                  {workflow.name || workflow.workflow_id}
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {workflow.trigger || "manual"}
                  </Badge>
                </CardTitle>
                {workflow.description ? (
                  <CardDescription>{workflow.description}</CardDescription>
                ) : null}
              </div>
              <p className="text-xs text-muted-foreground">
                {workflow.steps.length} step{workflow.steps.length === 1 ? "" : "s"}
              </p>
            </CardHeader>
            <CardContent>
              <WorkflowGraph workflow={workflow} onSelectStep={onStepClick} />
            </CardContent>
          </Card>

          <WorkflowEditor
            open={editorOpen}
            mode="edit"
            initial={workflow}
            onClose={() => setEditorOpen(false)}
            onSubmit={async (payload) => {
              await onSubmit(payload);
              setEditorOpen(false);
            }}
          />
        </>
      ) : null}
    </div>
  );
}
