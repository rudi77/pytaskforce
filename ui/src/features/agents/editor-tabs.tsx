import { useMemo } from "react";
import { Controller, useFieldArray } from "react-hook-form";
import type { Control, UseFormRegister, UseFormReturn } from "react-hook-form";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { FormField } from "@/components/FormField";
import { EmptyState } from "@/components/EmptyState";
import {
  useLLMModels,
  usePlanningStrategies,
  useSubagentCandidates,
  useTools,
  type ToolEntry,
} from "@/api/queries";
import type { ProfileFormValues } from "@/features/agents/schema";
import { cn } from "@/lib/utils";

interface TabProps {
  form: UseFormReturn<ProfileFormValues>;
  mode: "create" | "edit";
}

const fieldError = (form: UseFormReturn<ProfileFormValues>, path: string): string | undefined => {
  const segments = path.split(".");
  let cursor: unknown = form.formState.errors as unknown;
  for (const seg of segments) {
    if (!cursor || typeof cursor !== "object") return undefined;
    cursor = (cursor as Record<string, unknown>)[seg];
  }
  if (cursor && typeof cursor === "object" && "message" in (cursor as Record<string, unknown>)) {
    const msg = (cursor as { message?: unknown }).message;
    return typeof msg === "string" ? msg : undefined;
  }
  return undefined;
};

export function IdentityTab({ form, mode }: TabProps) {
  const reg = form.register;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField
        label="Profile id"
        htmlFor="name"
        required
        description="Becomes the filename. Letters, digits, dot, underscore, hyphen."
        error={fieldError(form, "name")}
        className="sm:col-span-1"
      >
        <Input
          id="name"
          placeholder="my-agent"
          disabled={mode === "edit"}
          {...reg("name")}
        />
      </FormField>
      <FormField
        label="Display name"
        htmlFor="display_name"
        required
        error={fieldError(form, "display_name")}
        className="sm:col-span-1"
      >
        <Input id="display_name" placeholder="My Agent" {...reg("display_name")} />
      </FormField>
      <FormField
        label="Description"
        htmlFor="description"
        error={fieldError(form, "description")}
        className="sm:col-span-2"
      >
        <Textarea
          id="description"
          rows={2}
          className="font-sans"
          placeholder="What does this agent do?"
          {...reg("description")}
        />
      </FormField>
      <FormField
        label="Specialist tag"
        htmlFor="specialist"
        description="Optional role tag (butler, accountant, …). Letters, digits, _ or -."
        error={fieldError(form, "specialist")}
        className="sm:col-span-1"
      >
        <Input id="specialist" placeholder="butler" {...reg("specialist")} />
      </FormField>
      <FormField
        label="System prompt"
        htmlFor="system_prompt"
        description="Inserted at the top of the agent context."
        error={fieldError(form, "system_prompt")}
        className="sm:col-span-2"
      >
        <Textarea
          id="system_prompt"
          rows={10}
          placeholder="You are a helpful assistant…"
          {...reg("system_prompt")}
        />
      </FormField>
    </div>
  );
}

export function ToolsTab({ form }: TabProps) {
  const { data, isLoading } = useTools();
  const tools = data?.tools ?? [];
  const selected = form.watch("tools");
  const setSelected = (next: string[]) =>
    form.setValue("tools", next, { shouldDirty: true });

  const toggle = (name: string) => {
    if (selected.includes(name)) {
      setSelected(selected.filter((t) => t !== name));
    } else {
      setSelected([...selected, name]);
    }
  };

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading tools…</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Selected ({selected.length})
        </span>
        {selected.length === 0 ? (
          <span className="text-sm text-muted-foreground">None — pick at least one below.</span>
        ) : (
          selected.map((name) => (
            <Badge key={name} variant="secondary" className="gap-1">
              <span>{name}</span>
              <button
                type="button"
                aria-label={`Remove ${name}`}
                onClick={() => toggle(name)}
                className="text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </Badge>
          ))
        )}
      </div>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {tools.map((tool) => (
          <ToolCheck
            key={tool.name}
            tool={tool}
            checked={selected.includes(tool.name)}
            onToggle={() => toggle(tool.name)}
          />
        ))}
      </ul>
    </div>
  );
}

function ToolCheck({
  tool,
  checked,
  onToggle,
}: {
  tool: ToolEntry;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <label
        className={cn(
          "flex cursor-pointer items-start gap-2 rounded-md border border-border p-3 transition-colors",
          checked ? "border-primary/40 bg-primary/5" : "hover:bg-accent",
        )}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="mt-0.5 h-4 w-4 accent-primary"
        />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{tool.name}</span>
          {tool.description ? (
            <span className="line-clamp-2 text-xs text-muted-foreground">
              {tool.description}
            </span>
          ) : null}
        </span>
        {tool.requires_approval ? (
          <Badge variant="warning" className="ml-1 px-1.5 py-0 text-[10px]">
            approval
          </Badge>
        ) : null}
      </label>
    </li>
  );
}

export function SubAgentsTab({ form, mode }: TabProps) {
  const { fields, append, remove } = useFieldArray({
    control: form.control as Control<ProfileFormValues>,
    name: "sub_agents",
  });
  const exclude = mode === "edit" ? form.watch("name") : undefined;
  const { data } = useSubagentCandidates(exclude);
  const candidates = data?.profiles ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Sub-agents can be invoked through the orchestration tools.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => append({ specialist: "", description: "" })}
        >
          <Plus className="h-4 w-4" />
          Add sub-agent
        </Button>
      </div>
      {fields.length === 0 ? (
        <EmptyState
          title="No sub-agents"
          description="Add a row to delegate work to another profile."
        />
      ) : (
        <ul className="space-y-3">
          {fields.map((field, index) => (
            <li
              key={field.id}
              className="grid grid-cols-1 gap-3 rounded-md border border-border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto]"
            >
              <FormField
                label="Profile"
                htmlFor={`sa-${index}-specialist`}
                error={fieldError(form, `sub_agents.${index}.specialist`)}
                required
              >
                <select
                  id={`sa-${index}-specialist`}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  {...form.register(`sub_agents.${index}.specialist`)}
                >
                  <option value="">— select —</option>
                  {candidates.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                      {c.specialist ? ` (${c.specialist})` : ""}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField
                label="Description"
                htmlFor={`sa-${index}-desc`}
                error={fieldError(form, `sub_agents.${index}.description`)}
              >
                <Input
                  id={`sa-${index}-desc`}
                  placeholder="When this sub-agent should be invoked"
                  {...form.register(`sub_agents.${index}.description`)}
                />
              </FormField>
              <div className="flex items-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => remove(index)}
                  aria-label="Remove sub-agent"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MCPTab({ form }: TabProps) {
  const { fields, append, remove } = useFieldArray({
    control: form.control as Control<ProfileFormValues>,
    name: "mcp_servers",
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Model Context Protocol servers exposed to this agent.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            append({
              type: "stdio",
              command: "",
              args: [] as { value: string }[],
              url: "",
              env: [] as { key: string; value: string }[],
              description: "",
            })
          }
        >
          <Plus className="h-4 w-4" />
          Add server
        </Button>
      </div>
      {fields.length === 0 ? (
        <EmptyState
          title="No MCP servers"
          description="Add a server to expose external tools (filesystem, browser, custom)."
        />
      ) : (
        <ul className="space-y-3">
          {fields.map((field, index) => (
            <MCPRow key={field.id} form={form} index={index} onRemove={() => remove(index)} />
          ))}
        </ul>
      )}
    </div>
  );
}

function MCPRow({
  form,
  index,
  onRemove,
}: {
  form: UseFormReturn<ProfileFormValues>;
  index: number;
  onRemove: () => void;
}) {
  const reg = form.register;
  const type = form.watch(`mcp_servers.${index}.type`);
  const envFields = useFieldArray({
    control: form.control as Control<ProfileFormValues>,
    name: `mcp_servers.${index}.env`,
  });
  const argsFields = useFieldArray({
    control: form.control as Control<ProfileFormValues>,
    name: `mcp_servers.${index}.args`,
  });

  return (
    <li className="space-y-3 rounded-md border border-border p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FormField label="Type" htmlFor={`mcp-${index}-type`}>
            <select
              id={`mcp-${index}-type`}
              className="flex h-8 rounded-md border border-input bg-transparent px-2 text-sm"
              {...reg(`mcp_servers.${index}.type`)}
            >
              <option value="stdio">stdio</option>
              <option value="sse">sse</option>
            </select>
          </FormField>
          <FormField label="Description" htmlFor={`mcp-${index}-desc`}>
            <Input
              id={`mcp-${index}-desc`}
              placeholder="(optional)"
              {...reg(`mcp_servers.${index}.description`)}
            />
          </FormField>
        </div>
        <Button type="button" variant="ghost" size="icon" onClick={onRemove}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      {type === "stdio" ? (
        <div className="grid gap-3 md:grid-cols-2">
          <FormField
            label="Command"
            htmlFor={`mcp-${index}-cmd`}
            required
            error={fieldError(form, `mcp_servers.${index}.command`)}
          >
            <Input
              id={`mcp-${index}-cmd`}
              placeholder="npx"
              {...reg(`mcp_servers.${index}.command`)}
            />
          </FormField>
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-sm font-medium">Args</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => argsFields.append({ value: "" })}
              >
                <Plus className="h-3 w-3" /> add
              </Button>
            </div>
            <div className="space-y-1.5">
              {argsFields.fields.map((af, ai) => (
                <div key={af.id} className="flex items-center gap-1.5">
                  <Input
                    {...reg(`mcp_servers.${index}.args.${ai}.value` as const)}
                    placeholder="--flag or value"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => argsFields.remove(ai)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
              {argsFields.fields.length === 0 ? (
                <p className="text-xs text-muted-foreground">No args.</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <FormField
          label="URL"
          htmlFor={`mcp-${index}-url`}
          required
          error={fieldError(form, `mcp_servers.${index}.url`)}
        >
          <Input
            id={`mcp-${index}-url`}
            placeholder="http://localhost:3000/mcp"
            {...reg(`mcp_servers.${index}.url`)}
          />
        </FormField>
      )}

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-sm font-medium">Environment variables</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => envFields.append({ key: "", value: "" })}
          >
            <Plus className="h-3 w-3" /> add
          </Button>
        </div>
        <div className="space-y-1.5">
          {envFields.fields.map((ef, ei) => (
            <div key={ef.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] gap-1.5">
              <Input placeholder="KEY" {...reg(`mcp_servers.${index}.env.${ei}.key` as const)} />
              <Input
                placeholder="value or ${ENV_VAR}"
                {...reg(`mcp_servers.${index}.env.${ei}.value` as const)}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => envFields.remove(ei)}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
          {envFields.fields.length === 0 ? (
            <p className="text-xs text-muted-foreground">None.</p>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function CommunicationTab({ form }: TabProps) {
  const reg = form.register;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField
        label="Default channel"
        htmlFor="comm-channel"
        description="e.g. telegram, teams, email"
      >
        <Input id="comm-channel" placeholder="telegram" {...reg("notification_channel")} />
      </FormField>
      <FormField
        label="Recipient id"
        htmlFor="comm-recipient"
        description="Telegram user id, Teams chat id, email address…"
      >
        <Input
          id="comm-recipient"
          placeholder="123456789"
          {...reg("notification_recipient_id")}
        />
      </FormField>
    </div>
  );
}

export function PlanningTab({ form }: TabProps) {
  const { data } = usePlanningStrategies();
  const strategies = data?.strategies ?? [];
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label="Strategy" htmlFor="planning_strategy">
        <select
          id="planning_strategy"
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          {...form.register("planning_strategy")}
        >
          {strategies.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
          {strategies.length === 0 ? (
            <option value="native_react">Native ReAct</option>
          ) : null}
        </select>
      </FormField>
      <FormField
        label="Max steps"
        htmlFor="max_steps"
        description="Hard cap on the ReAct loop length."
        error={fieldError(form, "max_steps")}
      >
        <Controller
          control={form.control}
          name="max_steps"
          render={({ field }) => (
            <Input
              id="max_steps"
              type="number"
              min={1}
              max={1000}
              value={field.value ?? ""}
              onChange={(e) => field.onChange(e.target.value === "" ? null : Number(e.target.value))}
            />
          )}
        />
      </FormField>
      <div className="sm:col-span-2 rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
        <strong className="font-medium text-foreground">Tip:</strong>{" "}
        {useMemo(() => {
          const current = form.watch("planning_strategy");
          return (
            strategies.find((s) => s.id === current)?.description ??
            "Pick a strategy to see its description."
          );
        }, [form, strategies])}
      </div>
    </div>
  );
}

export function LLMTab({ form }: TabProps) {
  const { data } = useLLMModels();
  const models = data?.models ?? [];
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField
        label="Default model"
        htmlFor="llm_default_model"
        description="Alias from llm_config.yaml"
      >
        <select
          id="llm_default_model"
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          {...form.register("llm_default_model")}
        >
          <option value="">— inherit from base profile —</option>
          {models.map((m) => (
            <option key={m.alias} value={m.alias}>
              {m.alias} → {m.model_id}
            </option>
          ))}
        </select>
      </FormField>
      <FormField
        label="Config path"
        htmlFor="llm_config_path"
        description="Override path to llm_config.yaml"
      >
        <Input
          id="llm_config_path"
          placeholder="src/taskforce/configs/llm_config.yaml"
          {...form.register("llm_config_path")}
        />
      </FormField>
    </div>
  );
}

export function ContextTab({ form }: TabProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField
        label="Max items"
        htmlFor="context_max_items"
        description="Number of context items the agent receives per LLM call."
        error={fieldError(form, "context_max_items")}
      >
        <Controller
          control={form.control}
          name="context_max_items"
          render={({ field }) => (
            <Input
              id="context_max_items"
              type="number"
              min={1}
              max={200}
              value={field.value ?? ""}
              onChange={(e) => field.onChange(e.target.value === "" ? null : Number(e.target.value))}
            />
          )}
        />
      </FormField>
      <FormField
        label="Max total chars"
        htmlFor="context_max_total_chars"
        description="Total context budget."
        error={fieldError(form, "context_max_total_chars")}
      >
        <Controller
          control={form.control}
          name="context_max_total_chars"
          render={({ field }) => (
            <Input
              id="context_max_total_chars"
              type="number"
              min={1000}
              max={200000}
              value={field.value ?? ""}
              onChange={(e) => field.onChange(e.target.value === "" ? null : Number(e.target.value))}
            />
          )}
        />
      </FormField>
    </div>
  );
}

export type { TabProps, UseFormRegister };
