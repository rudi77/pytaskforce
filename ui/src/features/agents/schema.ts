import { z } from "zod";

const NAME_PATTERN = /^[a-zA-Z0-9._-]+$/;
const SPECIALIST_PATTERN = /^[a-zA-Z0-9_-]+$/;

export const PLANNING_STRATEGIES = [
  "native_react",
  "plan_and_execute",
  "plan_and_react",
  "spar",
] as const;

export const mcpServerSchema = z
  .object({
    type: z.enum(["stdio", "sse"]),
    description: z.string(),
    command: z.string(),
    args: z.array(z.object({ value: z.string() })),
    url: z.string(),
    env: z.array(z.object({ key: z.string().min(1), value: z.string() })),
  })
  .refine((srv) => (srv.type === "stdio" ? !!srv.command : true), {
    message: "stdio server requires a command",
    path: ["command"],
  })
  .refine((srv) => (srv.type === "sse" ? !!srv.url : true), {
    message: "sse server requires a url",
    path: ["url"],
  });

export const subAgentSchema = z.object({
  specialist: z.string().min(1, "Pick a sub-agent profile"),
  description: z.string(),
});

export const profileFormSchema = z.object({
  name: z
    .string()
    .min(1, "Required")
    .max(128)
    .regex(NAME_PATTERN, "Use letters, digits, dot, underscore or hyphen only"),
  display_name: z.string().min(1, "Required").max(256),
  description: z.string().max(2048),
  specialist: z
    .string()
    .regex(SPECIALIST_PATTERN, "Letters, digits, _ or - only")
    .or(z.literal("")),
  system_prompt: z.string(),
  tools: z.array(z.string()),
  sub_agents: z.array(subAgentSchema),
  mcp_servers: z.array(mcpServerSchema),
  planning_strategy: z.enum(PLANNING_STRATEGIES),
  max_steps: z.number().int().min(1).max(1000).nullable(),
  llm_default_model: z.string(),
  llm_config_path: z.string(),
  context_max_items: z.number().int().min(1).max(200).nullable(),
  context_max_total_chars: z.number().int().min(1000).max(200_000).nullable(),
  notification_channel: z.string(),
  notification_recipient_id: z.string(),
});

export type ProfileFormValues = z.infer<typeof profileFormSchema>;

export const EMPTY_PROFILE_FORM: ProfileFormValues = {
  name: "",
  display_name: "",
  description: "",
  specialist: "",
  system_prompt: "",
  tools: [],
  sub_agents: [],
  mcp_servers: [],
  planning_strategy: "native_react",
  max_steps: 30,
  llm_default_model: "",
  llm_config_path: "",
  context_max_items: null,
  context_max_total_chars: null,
  notification_channel: "",
  notification_recipient_id: "",
};

interface BackendProfileConfig {
  description?: string;
  specialist?: string | null;
  system_prompt?: string;
  tools?: unknown[];
  sub_agents?: unknown[];
  mcp_servers?: unknown[];
  agent?: {
    name?: string;
    planning_strategy?: string;
    max_steps?: number | null;
  };
  llm?: { default_model?: string; config_path?: string };
  context_policy?: {
    max_items?: number | null;
    max_total_chars?: number | null;
  };
  notifications?: { default_channel?: string; default_recipient_id?: string };
  [key: string]: unknown;
}

export function profileConfigToForm(
  name: string,
  config: BackendProfileConfig,
): ProfileFormValues {
  const tools = (config.tools ?? [])
    .map((t) => (typeof t === "string" ? t : (t as { name?: string }).name))
    .filter((t): t is string => typeof t === "string" && t.length > 0);

  const subAgents = (config.sub_agents ?? [])
    .map((sa) => sa as { specialist?: string; description?: string })
    .filter((sa) => typeof sa.specialist === "string")
    .map((sa) => ({
      specialist: sa.specialist!,
      description: sa.description ?? "",
    }));

  const mcpServers = (config.mcp_servers ?? []).map((srv) => {
    const obj = (srv as Record<string, unknown>) ?? {};
    const env = obj.env && typeof obj.env === "object" ? (obj.env as Record<string, string>) : {};
    const args = Array.isArray(obj.args) ? (obj.args as unknown[]) : [];
    return {
      type: (obj.type === "sse" ? "sse" : "stdio") as "sse" | "stdio",
      description: typeof obj.description === "string" ? obj.description : "",
      command: typeof obj.command === "string" ? obj.command : "",
      args: args.map((a) => ({ value: String(a) })),
      url: typeof obj.url === "string" ? obj.url : "",
      env: Object.entries(env).map(([key, value]) => ({ key, value: String(value) })),
    };
  });

  const planningStrategy = (
    PLANNING_STRATEGIES.find((s) => s === config.agent?.planning_strategy) ??
    "native_react"
  ) as ProfileFormValues["planning_strategy"];

  return {
    name,
    display_name: config.agent?.name ?? name,
    description: config.description ?? "",
    specialist: config.specialist ?? "",
    system_prompt: config.system_prompt ?? "",
    tools,
    sub_agents: subAgents,
    mcp_servers: mcpServers,
    planning_strategy: planningStrategy,
    max_steps: config.agent?.max_steps ?? 30,
    llm_default_model: config.llm?.default_model ?? "",
    llm_config_path: config.llm?.config_path ?? "",
    context_max_items: config.context_policy?.max_items ?? null,
    context_max_total_chars: config.context_policy?.max_total_chars ?? null,
    notification_channel: config.notifications?.default_channel ?? "",
    notification_recipient_id: config.notifications?.default_recipient_id ?? "",
  };
}

export function formToProfileConfig(
  values: ProfileFormValues,
): Record<string, unknown> {
  const config: Record<string, unknown> = {};

  if (values.description) config.description = values.description;
  if (values.specialist) config.specialist = values.specialist;
  if (values.system_prompt) config.system_prompt = values.system_prompt;
  if (values.tools.length > 0) config.tools = values.tools;

  const subAgents = values.sub_agents
    .filter((sa) => sa.specialist)
    .map((sa) =>
      sa.description
        ? { specialist: sa.specialist, description: sa.description }
        : { specialist: sa.specialist },
    );
  if (subAgents.length > 0) config.sub_agents = subAgents;

  const mcpServers = values.mcp_servers.map((srv) => {
    const env = Object.fromEntries(
      srv.env.filter((entry) => entry.key.length > 0).map((entry) => [entry.key, entry.value]),
    );
    const args = srv.args.map((a) => a.value).filter((v) => v.length > 0);
    if (srv.type === "stdio") {
      const out: Record<string, unknown> = {
        type: "stdio",
        command: srv.command,
      };
      if (args.length > 0) out.args = args;
      if (Object.keys(env).length > 0) out.env = env;
      if (srv.description) out.description = srv.description;
      return out;
    }
    const out: Record<string, unknown> = { type: "sse", url: srv.url };
    if (Object.keys(env).length > 0) out.env = env;
    if (srv.description) out.description = srv.description;
    return out;
  });
  if (mcpServers.length > 0) config.mcp_servers = mcpServers;

  const agent: Record<string, unknown> = {
    name: values.display_name,
    planning_strategy: values.planning_strategy,
  };
  if (values.max_steps != null) agent.max_steps = values.max_steps;
  config.agent = agent;

  const llm: Record<string, unknown> = {};
  if (values.llm_default_model) llm.default_model = values.llm_default_model;
  if (values.llm_config_path) llm.config_path = values.llm_config_path;
  if (Object.keys(llm).length > 0) config.llm = llm;

  const contextPolicy: Record<string, unknown> = {};
  if (values.context_max_items != null) contextPolicy.max_items = values.context_max_items;
  if (values.context_max_total_chars != null)
    contextPolicy.max_total_chars = values.context_max_total_chars;
  if (Object.keys(contextPolicy).length > 0) config.context_policy = contextPolicy;

  if (values.notification_channel || values.notification_recipient_id) {
    const notifications: Record<string, unknown> = {};
    if (values.notification_channel) notifications.default_channel = values.notification_channel;
    if (values.notification_recipient_id)
      notifications.default_recipient_id = values.notification_recipient_id;
    config.notifications = notifications;
  }

  return config;
}
