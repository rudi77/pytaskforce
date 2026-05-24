import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import yaml from "js-yaml";
import {
  ArrowLeft20Regular,
  Checkmark16Regular,
  Code20Regular,
  Copy20Regular,
  Delete20Regular,
  Eye20Regular,
  EyeOff20Regular,
  Save20Regular,
  Warning16Regular,
  Warning20Regular,
} from "@fluentui/react-icons";

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
  useCloneProfile,
  useCreateProfile,
  useDeleteProfile,
  useProfile,
  useUpdateProfile,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import { useCurrentPermissions } from "@/lib/permissions";

interface Props {
  mode: "create" | "edit";
  profileName?: string;
}

const BASICS_TABS = [
  { id: "identity", label: "Identity" },
  { id: "tools", label: "Tools" },
  { id: "llm", label: "LLM" },
] as const;

const ADVANCED_TABS = [
  { id: "subagents", label: "Sub-agents" },
  { id: "mcp", label: "MCP" },
  { id: "communication", label: "Communication" },
  { id: "planning", label: "Planning" },
  { id: "context", label: "Context" },
] as const;

const PREVIEW_VISIBLE_KEY = "taskforce.editor.previewVisible";

export function AgentProfileEditor({ mode, profileName }: Props) {
  const navigate = useNavigate();
  const permissions = useCurrentPermissions();
  const profileQuery = useProfile(mode === "edit" ? profileName : undefined);
  const createMutation = useCreateProfile();
  const updateMutation = useUpdateProfile(profileName ?? "");
  const deleteMutation = useDeleteProfile();
  const cloneMutation = useCloneProfile();

  const [serverError, setServerError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [section, setSection] = useState<"basics" | "advanced">("basics");
  const [showPreview, setShowPreview] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(PREVIEW_VISIBLE_KEY) !== "0";
  });
  useEffect(() => {
    window.localStorage.setItem(PREVIEW_VISIBLE_KEY, showPreview ? "1" : "0");
  }, [showPreview]);

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

  const canCreateAgent = permissions.can("agent:create");
  const canUpdateAgent = permissions.can("agent:update");
  const canDeleteAgent = permissions.can("agent:delete");
  const canWriteCurrentMode = mode === "create" ? canCreateAgent : canUpdateAgent;
  const isReadOnlyProfile = mode === "edit" && profileQuery.data?.is_writable === false;
  const isWritable =
    (mode === "create" || profileQuery.data?.is_writable !== false) && canWriteCurrentMode;
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

  const onClone = async () => {
    if (!profileName) return;
    const suggestion = `${profileName}-copy`;
    const target = window.prompt(
      `Clone "${profileName}" to a user-owned profile.\nNew name:`,
      suggestion,
    );
    if (!target) return;
    setServerError(null);
    try {
      const created = await cloneMutation.mutateAsync({
        source: profileName,
        targetName: target.trim(),
      });
      navigate(`/agents/${encodeURIComponent(created.name)}`);
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" type="button" onClick={() => navigate("/agents")}>
          <ArrowLeft20Regular className="h-4 w-4" />
          All agents
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {savedAt ? (
            <Badge variant="success" className="gap-1">
              <Checkmark16Regular className="h-3 w-3" />
              Saved
            </Badge>
          ) : null}
          {isReadOnlyProfile ? (
            <Badge variant="warning" className="gap-1">
              <Warning16Regular className="h-3 w-3" />
              Read-only
            </Badge>
          ) : null}
          {isReadOnlyProfile && canCreateAgent ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClone}
              disabled={cloneMutation.isPending}
            >
              <Copy20Regular className="h-4 w-4" />
              Clone to user profile
            </Button>
          ) : null}
          {mode === "edit" && !isReadOnlyProfile && canDeleteAgent ? (
            <Button type="button" variant="outline" size="sm" onClick={onDelete} disabled={isBusy}>
              <Delete20Regular className="h-4 w-4" />
              Delete
            </Button>
          ) : null}
          <Button type="submit" disabled={isBusy || !isWritable}>
            <Save20Regular className="h-4 w-4" />
            {mode === "create" ? "Create" : "Save"}
          </Button>
        </div>
      </div>

      {serverError ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-3 text-sm text-destructive">{serverError}</CardContent>
        </Card>
      ) : null}

      {isReadOnlyProfile ? (
        <Card className="border-warning/40 bg-warning/5">
          <CardContent className="flex flex-wrap items-center gap-2 py-3 text-sm">
            <Warning20Regular className="h-4 w-4 text-warning" />
            <span>
              This profile ships with an agent package and is{" "}
              <strong>read-only</strong>. Use{" "}
              <span className="font-medium">"Clone to user profile"</span> to
              create an editable copy under <code>~/.taskforce/agents/</code>.
              {profileQuery.data?.format === "agent_md" ? (
                <>
                  {" "}
                  <em className="text-muted-foreground">
                    Note: cloning an <code>.agent.md</code> profile produces a
                    flat YAML — markdown body becomes <code>system_prompt</code>
                    and merged defaults are made explicit.
                  </em>
                </>
              ) : null}
            </span>
          </CardContent>
        </Card>
      ) : null}

      <div
        className={cn(
          "grid gap-5",
          showPreview ? "xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" : "",
        )}
      >
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-3">
            <div>
              <CardTitle>{mode === "create" ? "New profile" : profileName}</CardTitle>
              <CardDescription>
                {profileQuery.data?.path ? (
                  <span className="font-mono text-xs">{profileQuery.data.path}</span>
                ) : (
                  "Will be written to ~/.taskforce/agents/<name>.yaml"
                )}
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowPreview((v) => !v)}
              aria-pressed={showPreview}
              title={showPreview ? "Hide YAML preview" : "Show YAML preview"}
            >
              {showPreview ? (
                <EyeOff20Regular className="h-4 w-4" />
              ) : (
                <Eye20Regular className="h-4 w-4" />
              )}
              <span className="ml-1.5 text-xs font-medium">YAML preview</span>
            </Button>
          </CardHeader>
          <CardContent>
            <div className="mb-3 inline-flex rounded-md bg-muted p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setSection("basics")}
                className={cn(
                  "rounded px-3 py-1 font-medium transition-colors",
                  section === "basics"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                Basics
              </button>
              <button
                type="button"
                onClick={() => setSection("advanced")}
                className={cn(
                  "rounded px-3 py-1 font-medium transition-colors",
                  section === "advanced"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                Advanced
              </button>
            </div>
            <Tabs defaultValue={section === "basics" ? "identity" : "subagents"} key={section}>
              <TabsList className="flex-wrap">
                {(section === "basics" ? BASICS_TABS : ADVANCED_TABS).map((tab) => (
                  <TabsTrigger key={tab.id} value={tab.id}>
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
              {section === "basics" ? (
                <>
                  <TabsContent value="identity">
                    <IdentityTab form={form} mode={mode} />
                  </TabsContent>
                  <TabsContent value="tools">
                    <ToolsTab form={form} mode={mode} />
                  </TabsContent>
                  <TabsContent value="llm">
                    <LLMTab form={form} mode={mode} />
                  </TabsContent>
                </>
              ) : (
                <>
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
                  <TabsContent value="context">
                    <ContextTab form={form} mode={mode} />
                  </TabsContent>
                </>
              )}
            </Tabs>
          </CardContent>
        </Card>

        {showPreview ? (
        <Card className="xl:sticky xl:top-4 xl:self-start">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Code20Regular className="h-4 w-4" />
                YAML preview
              </CardTitle>
              <CardDescription>
                Live serialisation of the form. Save to write to disk.
              </CardDescription>
            </div>
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
        ) : null}
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
