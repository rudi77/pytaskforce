import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import yaml from "js-yaml";
import { ArrowLeft, Check, Save, Trash2, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  CommunicationTab,
  ContextTab,
  IdentityTab,
  LLMTab,
  MCPTab,
  PlanningTab,
  SubAgentsTab,
  ToolsTab,
} from "@/features/agents/editor-tabs";
import {
  EMPTY_PROFILE_FORM,
  formToProfileConfig,
  profileConfigToForm,
  profileFormSchema,
  type ProfileFormValues,
} from "@/features/agents/schema";
import {
  ProfileDetail,
  useCreateProfile,
  useDeleteProfile,
  useProfile,
  useUpdateProfile,
} from "@/api/queries";
import { ApiError } from "@/api/client";

interface Props {
  mode: "create" | "edit";
  profileName?: string;
}

const TABS = [
  { id: "identity", label: "Identity" },
  { id: "tools", label: "Tools" },
  { id: "subagents", label: "Sub-agents" },
  { id: "mcp", label: "MCP" },
  { id: "communication", label: "Communication" },
  { id: "planning", label: "Planning" },
  { id: "llm", label: "LLM" },
  { id: "context", label: "Context" },
] as const;

export function AgentProfileEditor({ mode, profileName }: Props) {
  const navigate = useNavigate();
  const profileQuery = useProfile(mode === "edit" ? profileName : undefined);
  const createMutation = useCreateProfile();
  const updateMutation = useUpdateProfile(profileName ?? "");
  const deleteMutation = useDeleteProfile();

  const [serverError, setServerError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: EMPTY_PROFILE_FORM,
    mode: "onBlur",
  });

  useEffect(() => {
    if (mode === "edit" && profileQuery.data) {
      form.reset(profileConfigToForm(profileQuery.data.name, profileQuery.data.config));
    }
  }, [mode, profileQuery.data, form]);

  const values = form.watch();
  const yamlPreview = useMemo(() => {
    try {
      return yaml.dump(formToProfileConfig(values), { noRefs: true, sortKeys: false });
    } catch (err) {
      return `# Could not preview YAML: ${(err as Error).message}`;
    }
  }, [values]);

  const isWritable = mode === "create" || profileQuery.data?.is_writable !== false;
  const isBusy = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  const onSubmit = form.handleSubmit(async (formValues) => {
    setServerError(null);
    const config = formToProfileConfig(formValues);
    try {
      if (mode === "create") {
        const created = await createMutation.mutateAsync({
          name: formValues.name,
          config,
        });
        setSavedAt(Date.now());
        navigate(`/agents/${encodeURIComponent(created.name)}`);
      } else {
        await updateMutation.mutateAsync({ config });
        setSavedAt(Date.now());
      }
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : (err as Error).message);
    }
  });

  const onDelete = async () => {
    if (!profileName) return;
    if (!window.confirm(`Delete profile "${profileName}"? This cannot be undone.`)) return;
    setServerError(null);
    try {
      await deleteMutation.mutateAsync(profileName);
      navigate("/agents");
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm" type="button">
          <Link to="/agents">
            <ArrowLeft className="h-4 w-4" />
            All agents
          </Link>
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {savedAt ? (
            <Badge variant="success" className="gap-1">
              <Check className="h-3 w-3" />
              Saved
            </Badge>
          ) : null}
          {!isWritable && mode === "edit" ? (
            <Badge variant="warning" className="gap-1">
              <AlertTriangle className="h-3 w-3" />
              Read-only
            </Badge>
          ) : null}
          {mode === "edit" && isWritable ? (
            <Button type="button" variant="outline" size="sm" onClick={onDelete} disabled={isBusy}>
              <Trash2 className="h-4 w-4" />
              Delete
            </Button>
          ) : null}
          <Button type="submit" disabled={isBusy || !isWritable}>
            <Save className="h-4 w-4" />
            {mode === "create" ? "Create" : "Save"}
          </Button>
        </div>
      </div>

      {serverError ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-3 text-sm text-destructive">{serverError}</CardContent>
        </Card>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{mode === "create" ? "New profile" : profileName}</CardTitle>
            <CardDescription>
              {profileQuery.data?.path ? (
                <span className="font-mono text-xs">{profileQuery.data.path}</span>
              ) : (
                "Will be written to ~/.taskforce/agents/<name>.yaml"
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="identity">
              <TabsList className="flex-wrap">
                {TABS.map((tab) => (
                  <TabsTrigger key={tab.id} value={tab.id}>
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value="identity">
                <IdentityTab form={form} mode={mode} />
              </TabsContent>
              <TabsContent value="tools">
                <ToolsTab form={form} mode={mode} />
              </TabsContent>
              <TabsContent value="subagents">
                <SubAgentsTab form={form} mode={mode} />
              </TabsContent>
              <TabsContent value="mcp">
                <MCPTab form={form} mode={mode} />
              </TabsContent>
              <TabsContent value="communication">
                <CommunicationTab form={form} mode={mode} />
              </TabsContent>
              <TabsContent value="planning">
                <PlanningTab form={form} mode={mode} />
              </TabsContent>
              <TabsContent value="llm">
                <LLMTab form={form} mode={mode} />
              </TabsContent>
              <TabsContent value="context">
                <ContextTab form={form} mode={mode} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <Card className="xl:sticky xl:top-4 xl:self-start">
          <CardHeader>
            <CardTitle>YAML preview</CardTitle>
            <CardDescription>
              Live serialisation of the form. Save to write to disk.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="max-h-[640px] overflow-auto scrollbar-thin rounded-md border border-border bg-muted/40 p-4 text-xs leading-relaxed">
              <code>{yamlPreview}</code>
            </pre>
            {mode === "edit" && profileQuery.data ? (
              <ServerYamlComparison detail={profileQuery.data} />
            ) : null}
          </CardContent>
        </Card>
      </div>
    </form>
  );
}

function ServerYamlComparison({ detail }: { detail: ProfileDetail }) {
  return (
    <details className="mt-3 rounded-md border border-border bg-muted/20 p-2 text-xs">
      <summary className="cursor-pointer text-muted-foreground">
        Show on-disk YAML (last save)
      </summary>
      <pre className="mt-2 max-h-72 overflow-auto scrollbar-thin">
        <code>{detail.yaml_text}</code>
      </pre>
    </details>
  );
}
