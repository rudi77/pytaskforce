import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/api/client";

export interface HealthResponse {
  status: string;
  version?: string;
  checks?: Record<string, unknown>;
  default_profile?: string | null;
}

export interface CustomAgent {
  source: "custom";
  agent_id: string;
  name: string;
  description: string;
  system_prompt: string;
  tool_allowlist: string[];
  mcp_servers: Record<string, unknown>[];
  mcp_tool_allowlist: string[];
  created_at: string;
  updated_at: string;
}

export interface ProfileAgent {
  source: "profile";
  profile: string;
  specialist: string | null;
  tools: (string | Record<string, unknown>)[];
  mcp_servers: Record<string, unknown>[];
  llm: Record<string, unknown>;
  persistence: Record<string, unknown>;
}

export interface PluginAgent {
  source: "plugin";
  agent_id: string;
  name: string;
  description: string;
  plugin_path: string;
  tool_classes: string[];
  specialist: string | null;
  mcp_servers: Record<string, unknown>[];
}

export type AgentSummary = CustomAgent | ProfileAgent | PluginAgent;

export interface AgentListResponse {
  agents: AgentSummary[];
}

export interface CreateCustomAgentPayload {
  agent_id: string;
  name: string;
  description: string;
  system_prompt: string;
  tool_allowlist: string[];
  mcp_servers?: Record<string, unknown>[];
  mcp_tool_allowlist?: string[];
}

export interface ProfileSummary {
  name: string;
  path: string;
  format: "agent_md" | "yaml";
  description: string;
  specialist: string | null;
  name_label: string | null;
  is_custom: boolean;
}

export interface ProfileDetail {
  name: string;
  path: string;
  format: "agent_md" | "yaml";
  description: string;
  specialist: string | null;
  is_writable?: boolean;
  config: Record<string, unknown>;
  yaml_text: string;
}

export interface ToolEntry {
  name: string;
  description?: string;
  parameters_schema?: Record<string, unknown>;
  requires_approval?: boolean;
  approval_risk_level?: string;
  origin?: string;
}

export interface ToolCatalogResponse {
  tools: ToolEntry[];
}

export interface SkillSummary {
  name: string;
  description: string;
  skill_type: "context" | "prompt" | "agent" | "library" | "integration";
  slash_name: string | null;
  file_path: string | null;
  allowed_tools: string[];
}

export interface PlanningStrategy {
  id: string;
  label: string;
  description: string;
}

export interface LLMModelEntry {
  alias: string;
  model_id: string;
  provider: string;
}

export interface LLMModelsResponse {
  default_model: string;
  models: LLMModelEntry[];
}

export interface FileMetadata {
  file_id: string;
  name: string;
  mime: string;
  size: number;
  sha256: string;
  created_at: string;
}

export interface ConversationInfo {
  conversation_id: string;
  channel: string;
  started_at: string;
  last_activity: string;
  message_count: number;
  topic: string | null;
  project_id: string | null;
}

export interface Project {
  project_id: string;
  name: string;
  path: string;
  created_at: string;
}

export type CreateProjectMode = "scratch" | "existing";

export interface CreateProjectInput {
  name: string;
  path: string;
  mode: CreateProjectMode;
}

export interface ConversationSummary {
  conversation_id: string;
  topic: string;
  summary: string;
  started_at: string;
  archived_at: string;
  message_count: number;
  project_id: string | null;
}

export interface ChatMessage {
  role: string;
  content: string;
  attachments?: FileMetadata[];
  /**
   * Optional rich-content parts (text + widgets) that take precedence over
   * `content` when present. Backend integration follows the A2UI shape — see
   * `features/chat/widgets/types.ts`.
   */
  parts?: import("@/features/chat/widgets/types").MessagePart[];
}

export const queryKeys = {
  health: ["health"] as const,
  agents: ["agents", "list"] as const,
  agent: (id: string) => ["agents", "detail", id] as const,
  agentActiveDeployment: (id: string, environment: string) =>
    ["agents", "deployment", "active", id, environment] as const,
  agentDeployments: (id: string) => ["agents", "deployment", "history", id] as const,
  tools: ["tools"] as const,
  profiles: ["profiles", "list"] as const,
  profile: (name: string) => ["profiles", "detail", name] as const,
  subagentCandidates: (exclude?: string) =>
    ["profiles", "subagent-candidates", exclude ?? null] as const,
  skills: ["skills"] as const,
  planningStrategies: ["planning-strategies"] as const,
  llmModels: ["llm", "models"] as const,
  acpPeers: ["acp", "peers"] as const,
  conversations: ["conversations", "list"] as const,
  conversationsByProject: (projectId: string) =>
    ["conversations", "list", "project", projectId] as const,
  archivedConversations: ["conversations", "archived"] as const,
  archivedConversationsByProject: (projectId: string) =>
    ["conversations", "archived", "project", projectId] as const,
  conversationMessages: (id: string) => ["conversations", "messages", id] as const,
  projects: ["projects", "list"] as const,
  project: (id: string) => ["projects", "detail", id] as const,
  filesystemBrowse: (path: string, includeHidden: boolean) =>
    ["filesystem", "browse", path, includeHidden] as const,
  settings: ["settings", "list"] as const,
  settingsSection: (section: string) => ["settings", "section", section] as const,
  oauthConnections: ["oauth", "connections"] as const,
};

// --- Agent deployments -----------------------------------------------------

export type DeploymentEnvironment = "local" | "staging" | "prod";
export type DeploymentStatus =
  | "pending"
  | "validating"
  | "deployed"
  | "failed"
  | "rolled_back";

export interface AgentDeployment {
  agent_id: string;
  version: string;
  status: DeploymentStatus;
  environment: DeploymentEnvironment;
  deployed_at: string | null;
  deployed_by: string | null;
  message: string | null;
  rollback_from: string | null;
  error: string | null;
  config_snapshot: Record<string, unknown>;
}

export interface DeploymentListResponse {
  deployments: AgentDeployment[];
}

export interface DeployAgentPayload {
  environment?: DeploymentEnvironment;
  deployed_by?: string | null;
  message?: string | null;
}

export interface RollbackAgentPayload {
  to_version: string;
  environment?: DeploymentEnvironment;
  deployed_by?: string | null;
  message?: string | null;
}

function invalidateDeploymentCaches(qc: ReturnType<typeof useQueryClient>, agentId: string) {
  qc.invalidateQueries({ queryKey: queryKeys.agentDeployments(agentId) });
  qc.invalidateQueries({ queryKey: ["agents", "deployment", "active", agentId] });
}

export function useActiveDeployment(
  agentId: string | undefined,
  environment: DeploymentEnvironment = "local",
) {
  return useQuery<AgentDeployment | null>({
    queryKey: queryKeys.agentActiveDeployment(agentId ?? "", environment),
    enabled: !!agentId,
    retry: 0,
    queryFn: async () => {
      try {
        return await apiFetch<AgentDeployment>(
          `/api/v1/agents/${encodeURIComponent(agentId!)}/active?environment=${environment}`,
        );
      } catch (err: unknown) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });
}

export function useDeploymentHistory(agentId: string | undefined) {
  return useQuery<DeploymentListResponse>({
    queryKey: queryKeys.agentDeployments(agentId ?? ""),
    enabled: !!agentId,
    queryFn: () =>
      apiFetch<DeploymentListResponse>(
        `/api/v1/agents/${encodeURIComponent(agentId!)}/deployments`,
      ),
  });
}

export function useDeployAgent(agentId: string) {
  const qc = useQueryClient();
  return useMutation<AgentDeployment, Error, DeployAgentPayload | void>({
    mutationFn: (payload) =>
      apiFetch<AgentDeployment>(`/api/v1/agents/${encodeURIComponent(agentId)}/deploy`, {
        method: "POST",
        body: payload ?? {},
      }),
    onSuccess: () => invalidateDeploymentCaches(qc, agentId),
  });
}

export function useRollbackAgent(agentId: string) {
  const qc = useQueryClient();
  return useMutation<AgentDeployment, Error, RollbackAgentPayload>({
    mutationFn: (payload) =>
      apiFetch<AgentDeployment>(`/api/v1/agents/${encodeURIComponent(agentId)}/rollback`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => invalidateDeploymentCaches(qc, agentId),
  });
}

export function useHealth(intervalMs = 10_000) {
  return useQuery<HealthResponse>({
    queryKey: queryKeys.health,
    queryFn: () => apiFetch<HealthResponse>("/health"),
    refetchInterval: intervalMs,
    retry: 0,
  });
}

export function useAgents() {
  return useQuery<AgentListResponse>({
    queryKey: queryKeys.agents,
    queryFn: () => apiFetch<AgentListResponse>("/api/v1/agents"),
  });
}

export function useCreateCustomAgent() {
  const qc = useQueryClient();
  return useMutation<CustomAgent, Error, CreateCustomAgentPayload>({
    mutationFn: (payload) =>
      apiFetch<CustomAgent>("/api/v1/agents", {
        method: "POST",
        body: payload,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.agents });
      qc.setQueryData(queryKeys.agent(data.agent_id), data);
    },
  });
}

export function useDeleteCustomAgent() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (agentId) =>
      apiFetch<void>(`/api/v1/agents/${encodeURIComponent(agentId)}`, {
        method: "DELETE",
      }),
    onSuccess: (_data, agentId) => {
      qc.invalidateQueries({ queryKey: queryKeys.agents });
      invalidateDeploymentCaches(qc, agentId);
      qc.removeQueries({ queryKey: queryKeys.agent(agentId) });
    },
  });
}

export function useProfiles() {
  return useQuery<{ profiles: ProfileSummary[] }>({
    queryKey: queryKeys.profiles,
    queryFn: () => apiFetch<{ profiles: ProfileSummary[] }>("/api/v1/profiles"),
  });
}

export function useProfile(name: string | undefined) {
  return useQuery<ProfileDetail>({
    queryKey: queryKeys.profile(name ?? ""),
    queryFn: () => apiFetch<ProfileDetail>(`/api/v1/profiles/${encodeURIComponent(name!)}`),
    enabled: !!name,
  });
}

export function useTools() {
  return useQuery<ToolCatalogResponse>({
    queryKey: queryKeys.tools,
    queryFn: () => apiFetch<ToolCatalogResponse>("/api/v1/tools"),
    // Tool catalog rarely changes during a session — cache for 5 minutes
    // so the wizard's three steps that consume it don't refetch needlessly.
    staleTime: 5 * 60 * 1000,
  });
}

export function useSkills() {
  return useQuery<{ skills: SkillSummary[] }>({
    queryKey: queryKeys.skills,
    queryFn: () => apiFetch<{ skills: SkillSummary[] }>("/api/v1/skills"),
    staleTime: 5 * 60 * 1000,
  });
}

export interface SkillDetail extends SkillSummary {
  body: string;
}

export function useSkill(name: string | undefined) {
  return useQuery<SkillDetail>({
    queryKey: ["skills", "detail", name ?? ""] as const,
    queryFn: () => apiFetch<SkillDetail>(`/api/v1/skills/${encodeURIComponent(name!)}`),
    enabled: !!name,
  });
}

export function usePlanningStrategies() {
  return useQuery<{ strategies: PlanningStrategy[] }>({
    queryKey: queryKeys.planningStrategies,
    queryFn: () =>
      apiFetch<{ strategies: PlanningStrategy[] }>("/api/v1/planning-strategies"),
    staleTime: 60 * 60 * 1000,
  });
}

export function useLLMModels() {
  return useQuery<LLMModelsResponse>({
    queryKey: queryKeys.llmModels,
    queryFn: () => apiFetch<LLMModelsResponse>("/api/v1/llm/models"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSubagentCandidates(exclude?: string) {
  return useQuery<{ profiles: ProfileSummary[] }>({
    queryKey: queryKeys.subagentCandidates(exclude),
    queryFn: () =>
      apiFetch<{ profiles: ProfileSummary[] }>(
        `/api/v1/profiles/available-as-subagent${exclude ? `?exclude=${encodeURIComponent(exclude)}` : ""}`,
      ),
  });
}

interface ProfileWritePayload {
  config: Record<string, unknown>;
}

interface ProfileCreatePayload extends ProfileWritePayload {
  name: string;
}

function invalidateProfileCaches(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: queryKeys.profiles });
  qc.invalidateQueries({ queryKey: queryKeys.agents });
  qc.invalidateQueries({ queryKey: ["profiles", "subagent-candidates"] });
}

export function useCreateProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileDetail, Error, ProfileCreatePayload>({
    mutationFn: (payload) =>
      apiFetch<ProfileDetail>("/api/v1/profiles", {
        method: "POST",
        body: payload,
      }),
    onSuccess: (data) => {
      invalidateProfileCaches(qc);
      qc.setQueryData(queryKeys.profile(data.name), data);
    },
  });
}

export function useUpdateProfile(name: string) {
  const qc = useQueryClient();
  return useMutation<ProfileDetail, Error, ProfileWritePayload>({
    mutationFn: (payload) =>
      apiFetch<ProfileDetail>(`/api/v1/profiles/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: payload,
      }),
    onSuccess: (data) => {
      invalidateProfileCaches(qc);
      qc.setQueryData(queryKeys.profile(name), data);
    },
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) =>
      apiFetch<void>(`/api/v1/profiles/${encodeURIComponent(name)}`, {
        method: "DELETE",
      }),
    onSuccess: () => invalidateProfileCaches(qc),
  });
}

export interface ProfileCloneInput {
  source: string;
  targetName: string;
}

export function useCloneProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileDetail, Error, ProfileCloneInput>({
    mutationFn: ({ source, targetName }) =>
      apiFetch<ProfileDetail>(
        `/api/v1/profiles/${encodeURIComponent(source)}/clone`,
        {
          method: "POST",
          body: { target_name: targetName },
        },
      ),
    onSuccess: (data) => {
      invalidateProfileCaches(qc);
      qc.setQueryData(queryKeys.profile(data.name), data);
    },
  });
}

export function useConversations(projectId?: string) {
  return useQuery<ConversationInfo[]>({
    queryKey: projectId
      ? queryKeys.conversationsByProject(projectId)
      : queryKeys.conversations,
    queryFn: () =>
      apiFetch<ConversationInfo[]>("/api/v1/conversations", {
        query: projectId ? { project_id: projectId } : undefined,
      }),
  });
}

export function useArchivedConversations(
  limit = 20,
  projectId?: string,
) {
  return useQuery<ConversationSummary[]>({
    queryKey: projectId
      ? queryKeys.archivedConversationsByProject(projectId)
      : queryKeys.archivedConversations,
    queryFn: () =>
      apiFetch<ConversationSummary[]>("/api/v1/conversations/archived", {
        query: projectId ? { limit, project_id: projectId } : { limit },
      }),
  });
}

export function useConversationMessages(id: string | undefined) {
  return useQuery<ChatMessage[]>({
    queryKey: queryKeys.conversationMessages(id ?? ""),
    queryFn: () =>
      apiFetch<ChatMessage[]>(
        `/api/v1/conversations/${encodeURIComponent(id!)}/messages`,
      ),
    enabled: !!id,
  });
}

interface CreateConversationInput {
  channel?: string;
  sender_id?: string;
  project_id?: string | null;
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation<ConversationInfo, Error, CreateConversationInput | void>({
    mutationFn: (payload) =>
      apiFetch<ConversationInfo>("/api/v1/conversations", {
        method: "POST",
        body: payload ?? { channel: "rest" },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.conversations }),
  });
}

// --- Projects --------------------------------------------------------------

export function useProjects() {
  return useQuery<Project[]>({
    queryKey: queryKeys.projects,
    queryFn: () => apiFetch<Project[]>("/api/v1/projects"),
  });
}

export function useProject(id: string | undefined) {
  return useQuery<Project>({
    queryKey: queryKeys.project(id ?? ""),
    queryFn: () =>
      apiFetch<Project>(`/api/v1/projects/${encodeURIComponent(id!)}`),
    enabled: !!id,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation<Project, Error, CreateProjectInput>({
    mutationFn: (payload) =>
      apiFetch<Project>("/api/v1/projects", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (projectId) =>
      apiFetch<void>(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects }),
  });
}

export interface FilesystemEntry {
  name: string;
  path: string;
}

export interface FilesystemBrowseResponse {
  path: string;
  parent: string | null;
  entries: FilesystemEntry[];
  drives: string[];
  is_windows: boolean;
}

export function useBrowseFilesystem(
  path: string,
  options: { includeHidden?: boolean; enabled?: boolean } = {},
) {
  const includeHidden = options.includeHidden ?? false;
  const enabled = options.enabled ?? true;
  return useQuery<FilesystemBrowseResponse, ApiError>({
    queryKey: queryKeys.filesystemBrowse(path, includeHidden),
    queryFn: () => {
      const params = new URLSearchParams();
      if (path) params.set("path", path);
      if (includeHidden) params.set("include_hidden", "true");
      const qs = params.toString();
      return apiFetch<FilesystemBrowseResponse>(
        `/api/v1/filesystem/browse${qs ? `?${qs}` : ""}`,
      );
    },
    enabled,
    staleTime: 10_000,
  });
}

export interface ForkConversationInput {
  conversationId: string;
  upToIndex?: number;
}

export interface ForkConversationResult {
  conversation_id: string;
  source_id: string;
  messages_copied: number;
}

export function useForkConversation() {
  const qc = useQueryClient();
  return useMutation<ForkConversationResult, Error, ForkConversationInput>({
    mutationFn: ({ conversationId, upToIndex }) =>
      apiFetch<ForkConversationResult>(
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/fork`,
        {
          method: "POST",
          body: { up_to_index: upToIndex ?? null, channel: "rest" },
        },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.conversations }),
  });
}

export function useArchiveConversation() {
  const qc = useQueryClient();
  return useMutation<void, Error, { id: string; summary?: string }>({
    mutationFn: ({ id, summary }) =>
      apiFetch<void>(`/api/v1/conversations/${encodeURIComponent(id)}/archive`, {
        method: "POST",
        body: summary ? { summary } : {},
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.conversations });
      qc.invalidateQueries({ queryKey: queryKeys.archivedConversations });
    },
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation<void, Error, { id: string }>({
    mutationFn: ({ id }) =>
      apiFetch<void>(`/api/v1/conversations/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    // The DELETE applies to either an active or an archived conversation —
    // invalidate both list shapes (global + per-project) so any open page
    // refetches the right slice without us having to know which one the
    // caller is on.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}

export function useRenameConversation() {
  const qc = useQueryClient();
  return useMutation<ConversationInfo, Error, { id: string; title: string }>({
    mutationFn: ({ id, title }) =>
      apiFetch<ConversationInfo>(
        `/api/v1/conversations/${encodeURIComponent(id)}`,
        { method: "PATCH", body: { title } },
      ),
    // Rename may target an active OR archived conversation; invalidate
    // every keyspace under "conversations" so both sidebar buckets refresh.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}

export interface CompactConversationResult {
  status: "compacted" | "skipped";
  summarized?: number;
  kept?: number;
  summary_preview?: string | null;
  reason?: string | null;
  messages?: number | null;
}

export function useCompactConversation() {
  const qc = useQueryClient();
  return useMutation<
    CompactConversationResult,
    Error,
    { id: string; keepLastN?: number }
  >({
    mutationFn: ({ id, keepLastN }) =>
      apiFetch<CompactConversationResult>(
        `/api/v1/conversations/${encodeURIComponent(id)}/compact`,
        {
          method: "POST",
          body: { keep_last_n: keepLastN ?? 4 },
        },
      ),
    onSuccess: (_data, variables) => {
      // Invalidate both the message log and the conversation list so the
      // sidebar's message_count refreshes too.
      qc.invalidateQueries({
        queryKey: queryKeys.conversationMessages(variables.id),
      });
      qc.invalidateQueries({ queryKey: queryKeys.conversations });
    },
  });
}

export interface TokenUsageBucket {
  bucket: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  call_count: number;
}

export interface TokenUsageResponse {
  granularity: string;
  pricing_as_of: string | null;
  buckets: TokenUsageBucket[];
}

export interface AgentUsageEntry {
  agent: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface ModelUsageEntry {
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface CostSummaryResponse {
  today_usd: number;
  week_usd: number;
  month_usd: number;
  pricing_as_of: string | null;
  by_agent: AgentUsageEntry[];
  by_model: ModelUsageEntry[];
}

export interface ActiveRun {
  session_id: string;
  started_at: string;
  profile: string | null;
  agent_id: string | null;
  conversation_id: string | null;
  mission_preview: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  last_event: string;
  last_event_at: string;
}

export interface ActiveRunsResponse {
  runs: ActiveRun[];
}

export function useTokenUsage(params?: {
  granularity?: "day" | "hour" | "minute";
  from?: string;
  to?: string;
  agent?: string;
}) {
  const { granularity = "day", from, to, agent } = params ?? {};
  return useQuery<TokenUsageResponse>({
    queryKey: ["analytics", "token-usage", granularity, from ?? null, to ?? null, agent ?? null] as const,
    queryFn: () =>
      apiFetch<TokenUsageResponse>("/api/v1/analytics/token-usage", {
        query: { granularity, from, to, agent },
      }),
    staleTime: 30_000,
  });
}

export function useCostSummary() {
  return useQuery<CostSummaryResponse>({
    queryKey: ["analytics", "cost-summary"] as const,
    queryFn: () => apiFetch<CostSummaryResponse>("/api/v1/analytics/cost-summary"),
    staleTime: 30_000,
  });
}

export function useActiveRuns(intervalMs = 4_000) {
  return useQuery<ActiveRunsResponse>({
    queryKey: ["runs", "active"] as const,
    queryFn: () => apiFetch<ActiveRunsResponse>("/api/v1/runs/active"),
    refetchInterval: intervalMs,
  });
}

export interface TraceEvent {
  timestamp: string;
  event_type: string;
  message?: string;
  details?: Record<string, unknown> | null;
  step?: number | null;
}

export interface RunTrace {
  session_id: string;
  started_at: string;
  profile?: string | null;
  agent_id?: string | null;
  mission: string;
  finished: boolean;
  final_status?: string | null;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost_usd: number;
  events: TraceEvent[];
}

export interface RecentRunSummary {
  session_id: string;
  started_at: string;
  profile?: string | null;
  agent_id?: string | null;
  mission_preview: string;
  finished: boolean;
  final_status?: string | null;
  event_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost_usd: number;
}

export function useRecentRuns(intervalMs = 6_000) {
  return useQuery<{ runs: RecentRunSummary[] }>({
    queryKey: ["runs", "recent"] as const,
    queryFn: () => apiFetch<{ runs: RecentRunSummary[] }>("/api/v1/runs/recent"),
    refetchInterval: intervalMs,
  });
}

export function useRunTrace(sessionId: string | undefined, intervalMs = 3_000) {
  return useQuery<RunTrace>({
    queryKey: ["runs", "trace", sessionId ?? ""] as const,
    queryFn: () =>
      apiFetch<RunTrace>(`/api/v1/runs/${encodeURIComponent(sessionId!)}/trace`),
    enabled: !!sessionId,
    retry: (failureCount, error) => {
      // Stop retrying on 404 — the trace was evicted or never existed.
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 1;
    },
    refetchInterval: (query) => {
      // Stop polling on errors (especially 404) so an evicted trace
      // doesn't keep hammering the server forever.
      if (query.state.status === "error") return false;
      const data = (query.state as { data?: RunTrace }).data;
      if (data?.finished) return false;
      return intervalMs;
    },
  });
}

export function useCancelRun() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (sessionId) =>
      apiFetch<void>(`/api/v1/execute/${encodeURIComponent(sessionId)}/cancel`, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", "active"] }),
  });
}

export interface AcpPeer {
  name: string;
  agent: string;
  base_url: string;
  description: string;
  auth_type: "none" | "bearer" | "mtls" | string;
  token_env: string | null;
}

export interface AcpPeerInput {
  name: string;
  base_url: string;
  agent: string;
  description?: string;
  auth: {
    type: "none" | "bearer" | "mtls";
    token_env?: string | null;
    token?: string | null;
  };
}

export interface AcpTestResult {
  ok: boolean;
  status_code?: number | null;
  latency_ms: number;
  agent?: string | null;
  base_url?: string | null;
  error?: string | null;
}

export function useAcpPeers() {
  return useQuery<AcpPeer[]>({
    queryKey: queryKeys.acpPeers,
    queryFn: () => apiFetch<AcpPeer[]>("/api/v1/acp/peers"),
  });
}

export function useCreateAcpPeer() {
  const qc = useQueryClient();
  return useMutation<AcpPeer, Error, AcpPeerInput>({
    mutationFn: (payload) =>
      apiFetch<AcpPeer>("/api/v1/acp/peers", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.acpPeers }),
  });
}

export function useUpdateAcpPeer() {
  const qc = useQueryClient();
  return useMutation<AcpPeer, Error, { name: string; payload: Omit<AcpPeerInput, "name"> }>({
    mutationFn: ({ name, payload }) =>
      apiFetch<AcpPeer>(`/api/v1/acp/peers/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: payload,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.acpPeers }),
  });
}

export function useDeleteAcpPeer() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) =>
      apiFetch<void>(`/api/v1/acp/peers/${encodeURIComponent(name)}`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.acpPeers }),
  });
}

export function useTestAcpPeer() {
  return useMutation<AcpTestResult, Error, string>({
    mutationFn: (name) =>
      apiFetch<AcpTestResult>(
        `/api/v1/acp/peers/${encodeURIComponent(name)}/test`,
        { method: "POST" },
      ),
  });
}

export interface McpProbeRequest {
  type: "stdio" | "sse";
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
}

export interface McpProbeTool {
  name: string;
  description?: string;
  input_schema?: Record<string, unknown> | null;
}

export interface McpProbeResult {
  ok: boolean;
  elapsed_ms: number;
  tools: McpProbeTool[];
  error?: string | null;
}

export function useProbeMcp() {
  return useMutation<McpProbeResult, Error, McpProbeRequest>({
    mutationFn: (payload) =>
      apiFetch<McpProbeResult>("/api/v1/mcp/probe", {
        method: "POST",
        body: payload,
      }),
  });
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  emoji: string;
  persona_hint: string;
  recommended_tools: string[];
  recommended_skills: string[];
  system_prompt_template: string;
  example_prompts: string[];
  tone_default: string;
  language_default: string;
}

export function useAgentTemplates() {
  return useQuery<{ templates: AgentTemplate[] }>({
    queryKey: ["agent-templates", "list"] as const,
    queryFn: () =>
      apiFetch<{ templates: AgentTemplate[] }>("/api/v1/agent-templates"),
    staleTime: 5 * 60 * 1000,
  });
}

export interface ComposePromptInput {
  template_id?: string | null;
  description?: string;
  tone?: string;
  language?: string;
  rules?: string;
  use_ai?: boolean;
}

export interface ComposePromptResponse {
  system_prompt: string;
  used_ai: boolean;
  ai_attempted?: boolean;
  ai_error?: string | null;
}

export function useComposePrompt() {
  return useMutation<ComposePromptResponse, Error, ComposePromptInput>({
    mutationFn: (payload) =>
      apiFetch<ComposePromptResponse>(
        "/api/v1/agent-templates/compose-prompt",
        { method: "POST", body: payload },
      ),
  });
}

export interface EvalCellResult {
  profile: string;
  mission: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  latency_ms?: number | null;
  final_message: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  error?: string | null;
  session_id?: string | null;
}

export interface EvalRun {
  run_id: string;
  missions: string[];
  profiles: string[];
  created_at: string;
  finished: boolean;
  cells: EvalCellResult[];
}

export interface EvalRunSummary {
  run_id: string;
  missions: string[];
  profiles: string[];
  created_at: string;
  finished: boolean;
  cell_count: number;
  completed_cells: number;
}

export interface CreateEvalRunInput {
  missions: string[];
  profiles: string[];
  parallelism?: number;
  cell_timeout_s?: number;
}

export function useEvalRuns(intervalMs = 4_000) {
  return useQuery<{ runs: EvalRunSummary[] }>({
    queryKey: ["evals", "list"] as const,
    queryFn: () => apiFetch<{ runs: EvalRunSummary[] }>("/api/v1/evals/runs"),
    refetchInterval: intervalMs,
  });
}

export function useEvalRun(runId: string | undefined, intervalMs = 2_000) {
  return useQuery<EvalRun>({
    queryKey: ["evals", "detail", runId ?? ""] as const,
    queryFn: () =>
      apiFetch<EvalRun>(`/api/v1/evals/runs/${encodeURIComponent(runId!)}`),
    enabled: !!runId,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 1;
    },
    refetchInterval: (query) => {
      if (query.state.status === "error") return false;
      const data = (query.state as { data?: EvalRun }).data;
      if (data?.finished) return false;
      return intervalMs;
    },
  });
}

export function useCreateEvalRun() {
  const qc = useQueryClient();
  return useMutation<{ run_id: string; cell_count: number }, Error, CreateEvalRunInput>({
    mutationFn: (payload) =>
      apiFetch<{ run_id: string; cell_count: number }>("/api/v1/evals/runs", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evals", "list"] }),
  });
}

// --- Workflows -------------------------------------------------------------

/**
 * One step in a {@link WorkflowDefinition}. Mirrors `WorkflowStepRequest`
 * in `src/taskforce/api/routes/workflows.py`.
 */
export interface WorkflowStep {
  step_id: string;
  agent: string;
  task: string;
  depends_on: string[];
  metadata: Record<string, unknown>;
  acp_peer?: string | null;
}

/**
 * First-class workflow definition (ADR-022 §7). Mirrors
 * `WorkflowDefinitionRequest` and `WorkflowDefinition.to_dict`.
 */
export interface WorkflowDefinition {
  workflow_id: string;
  name: string;
  description: string;
  trigger: string;
  trigger_config: Record<string, unknown>;
  steps: WorkflowStep[];
  metadata: Record<string, unknown>;
}

export interface SaveWorkflowResponse {
  success: boolean;
  workflow: WorkflowDefinition;
  scheduled_job_id: string | null;
}

export interface WorkflowStepResult {
  step_id: string;
  agent: string;
  task: string;
  status?: string;
  output?: string | null;
  error?: string | null;
  [key: string]: unknown;
}

export interface RunWorkflowResponse {
  success: boolean;
  workflow_id: string;
  steps: WorkflowStepResult[];
}

export const workflowQueryKeys = {
  list: ["workflows", "list"] as const,
  detail: (id: string) => ["workflows", "detail", id] as const,
};

export function useWorkflowDefinitions() {
  return useQuery<{ workflows: WorkflowDefinition[] }>({
    queryKey: workflowQueryKeys.list,
    queryFn: () =>
      apiFetch<{ workflows: WorkflowDefinition[] }>("/api/v1/workflows/definitions"),
  });
}

export function useWorkflowDefinition(id: string | undefined) {
  return useQuery<{ workflow: WorkflowDefinition }>({
    queryKey: workflowQueryKeys.detail(id ?? ""),
    queryFn: () =>
      apiFetch<{ workflow: WorkflowDefinition }>(
        `/api/v1/workflows/definitions/${encodeURIComponent(id!)}`,
      ),
    enabled: !!id,
  });
}

export function useSaveWorkflowDefinition() {
  const qc = useQueryClient();
  return useMutation<SaveWorkflowResponse, Error, WorkflowDefinition>({
    mutationFn: (payload) =>
      apiFetch<SaveWorkflowResponse>("/api/v1/workflows/definitions", {
        method: "POST",
        body: payload,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: workflowQueryKeys.list });
      qc.setQueryData(workflowQueryKeys.detail(data.workflow.workflow_id), {
        workflow: data.workflow,
      });
    },
  });
}

export function useDeleteWorkflowDefinition() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (workflowId) =>
      apiFetch<void>(
        `/api/v1/workflows/definitions/${encodeURIComponent(workflowId)}`,
        { method: "DELETE" },
      ),
    onSuccess: (_data, workflowId) => {
      qc.invalidateQueries({ queryKey: workflowQueryKeys.list });
      qc.removeQueries({ queryKey: workflowQueryKeys.detail(workflowId) });
    },
  });
}

export function useRunWorkflowDefinition() {
  return useMutation<RunWorkflowResponse, Error, { workflowId: string; sessionId?: string }>({
    mutationFn: ({ workflowId, sessionId }) =>
      apiFetch<RunWorkflowResponse>(
        `/api/v1/workflows/definitions/${encodeURIComponent(workflowId)}/run`,
        {
          method: "POST",
          body: { session_id: sessionId ?? null },
        },
      ),
  });
}

export function useUploadFile() {
  return useMutation<FileMetadata, Error, File>({
    mutationFn: (file) => {
      const data = new FormData();
      data.append("file", file);
      return apiFetch<FileMetadata>("/api/v1/files", {
        method: "POST",
        body: data,
      });
    },
  });
}

// ----- Settings (UI-managed runtime config) --------------------------------

export interface SettingsListResponse {
  sections: string[];
  known_sections: string[];
}

export interface SettingsSectionResponse<T = Record<string, unknown>> {
  name: string;
  data: T;
  is_known: boolean;
}

export interface ConnectionTestResult {
  ok: boolean;
  detail: string;
}

export function useSettingsIndex() {
  return useQuery<SettingsListResponse>({
    queryKey: queryKeys.settings,
    queryFn: () => apiFetch<SettingsListResponse>("/api/v1/settings"),
  });
}

export function useSettingsSection<T = Record<string, unknown>>(section: string | undefined) {
  return useQuery<SettingsSectionResponse<T> | null>({
    queryKey: section ? queryKeys.settingsSection(section) : ["settings", "section", "__none__"],
    enabled: Boolean(section),
    queryFn: async () => {
      try {
        return await apiFetch<SettingsSectionResponse<T>>(
          `/api/v1/settings/${encodeURIComponent(section!)}`,
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
  });
}

export function useUpdateSettingsSection<T = Record<string, unknown>>() {
  const qc = useQueryClient();
  return useMutation<SettingsSectionResponse<T>, Error, { section: string; data: T }>({
    mutationFn: ({ section, data }) =>
      apiFetch<SettingsSectionResponse<T>>(
        `/api/v1/settings/${encodeURIComponent(section)}`,
        {
          method: "PUT",
          body: { data },
        },
      ),
    onSuccess: (resp) => {
      qc.setQueryData(queryKeys.settingsSection(resp.name), resp);
      qc.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}

export function useDeleteSettingsSection() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (section) =>
      apiFetch<void>(`/api/v1/settings/${encodeURIComponent(section)}`, {
        method: "DELETE",
      }),
    onSuccess: (_void, section) => {
      qc.removeQueries({ queryKey: queryKeys.settingsSection(section) });
      qc.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}

export function useTestLLMProvider() {
  return useMutation<ConnectionTestResult, Error, string>({
    mutationFn: (provider) =>
      apiFetch<ConnectionTestResult>(
        `/api/v1/settings/llm-providers/${encodeURIComponent(provider)}/test`,
        { method: "POST" },
      ),
  });
}

export function useTestChannel() {
  return useMutation<
    ConnectionTestResult,
    Error,
    { channel: string; recipient: string; message?: string }
  >({
    mutationFn: ({ channel, recipient, message }) =>
      apiFetch<ConnectionTestResult>(
        `/api/v1/settings/channels/${encodeURIComponent(channel)}/test`,
        {
          method: "POST",
          body: { recipient, message: message ?? "Taskforce test message — channel is wired up." },
        },
      ),
  });
}

// ----- Channel bots (multi-bot per channel) --------------------------------

export type BotOwnerKind = "tenant" | "user";
export type PairingMode = "implicit" | "paired" | "anonymous";

export interface BotConfig {
  id: string;
  channel_type: string;
  bot_token: string;
  owner_kind: BotOwnerKind;
  owner_user_id: string | null;
  default_agent: string | null;
  pairing_mode: PairingMode | null;
  enabled: boolean;
}

export interface BotListResponse {
  bots: BotConfig[];
}

export const channelBotKeys = {
  list: ["settings", "channels", "bots"] as const,
};

export function useChannelBots() {
  return useQuery<BotListResponse>({
    queryKey: channelBotKeys.list,
    queryFn: () => apiFetch<BotListResponse>("/api/v1/settings/channels/bots"),
  });
}

const BOT_POLLERS_KEY = ["settings", "channels", "bot-pollers"] as const;

function invalidateBotsAndPollers(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: channelBotKeys.list });
  qc.invalidateQueries({ queryKey: BOT_POLLERS_KEY });
}

export function useCreateChannelBot() {
  const qc = useQueryClient();
  return useMutation<BotConfig, Error, BotConfig>({
    mutationFn: (bot) =>
      apiFetch<BotConfig>("/api/v1/settings/channels/bots", {
        method: "POST",
        body: bot,
      }),
    onSuccess: () => invalidateBotsAndPollers(qc),
  });
}

export function useUpdateChannelBot() {
  const qc = useQueryClient();
  return useMutation<BotConfig, Error, BotConfig>({
    mutationFn: (bot) =>
      apiFetch<BotConfig>(
        `/api/v1/settings/channels/bots/${encodeURIComponent(bot.id)}`,
        {
          method: "PATCH",
          body: bot,
        },
      ),
    onSuccess: () => invalidateBotsAndPollers(qc),
  });
}

export function useDeleteChannelBot() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (botId) =>
      apiFetch<void>(`/api/v1/settings/channels/bots/${encodeURIComponent(botId)}`, {
        method: "DELETE",
      }),
    onSuccess: () => invalidateBotsAndPollers(qc),
  });
}

export function useTestChannelBot() {
  return useMutation<
    ConnectionTestResult,
    Error,
    { botId: string; recipient: string; message?: string }
  >({
    mutationFn: ({ botId, recipient, message }) =>
      apiFetch<ConnectionTestResult>(
        `/api/v1/settings/channels/bots/${encodeURIComponent(botId)}/test`,
        {
          method: "POST",
          body: {
            recipient,
            message: message ?? "Taskforce test message — bot is wired up.",
          },
        },
      ),
  });
}

export interface BotPollerStatusResponse {
  running_bot_ids: string[];
}

export function useBotPollerStatus() {
  return useQuery<BotPollerStatusResponse>({
    queryKey: ["settings", "channels", "bot-pollers"] as const,
    queryFn: () =>
      apiFetch<BotPollerStatusResponse>("/api/v1/settings/channels/bot-pollers"),
    // Refetch after mutations and on a short interval so the UI reflects
    // hot-reconcile results within a couple of seconds.
    refetchInterval: 5_000,
  });
}

// ----- OAuth connections ---------------------------------------------------

export interface OAuthConnection {
  provider: string;
  status: string;
  scopes: string[];
  has_refresh_token: boolean;
  expires_at: string | null;
  is_expired: boolean;
}

export interface OAuthConnectionsResponse {
  connections: OAuthConnection[];
  auth_manager_available: boolean;
}

export function useOAuthConnections() {
  return useQuery<OAuthConnectionsResponse>({
    queryKey: queryKeys.oauthConnections,
    queryFn: () => apiFetch<OAuthConnectionsResponse>("/api/v1/oauth/connections"),
  });
}

export function useRevokeOAuthConnection() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (provider) =>
      apiFetch<void>(`/api/v1/oauth/connections/${encodeURIComponent(provider)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.oauthConnections });
    },
  });
}

// ----- Visible-agents helper (consumes existing /agents endpoint) ----------

export function useAllAgentsForVisibility() {
  return useQuery<AgentListResponse>({
    queryKey: ["agents", "list", "include_hidden"] as const,
    queryFn: () =>
      apiFetch<AgentListResponse>("/api/v1/agents?include_hidden=true"),
  });
}

// ----- Workspace browse (Cowork-parity @mention picker) -------------------

export interface WorkspaceEntry {
  path: string;
  name: string;
  type: "file" | "dir";
  size?: number | null;
}

export interface WorkspaceListResponse {
  root: string;
  path: string;
  entries: WorkspaceEntry[];
  truncated: boolean;
}

export interface BrowseWorkspaceArgs {
  path?: string;
  q?: string;
  includeHidden?: boolean;
  limit?: number;
}

/**
 * Mounts the workspace browse endpoint into React-Query so the picker can
 * stay responsive (cached per directory + filter combo). The endpoint is
 * cheap (single ``iterdir``) so a short ``staleTime`` is fine.
 */
export function useWorkspaceBrowse(
  args: BrowseWorkspaceArgs,
  enabled = true,
) {
  const { path = "", q = "", includeHidden = false, limit = 200 } = args;
  return useQuery<WorkspaceListResponse>({
    queryKey: ["workspace", "browse", path, q, includeHidden, limit] as const,
    queryFn: () => {
      const params = new URLSearchParams();
      if (path) params.set("path", path);
      if (q) params.set("q", q);
      if (includeHidden) params.set("include_hidden", "true");
      if (limit !== 200) params.set("limit", String(limit));
      const qs = params.toString();
      return apiFetch<WorkspaceListResponse>(
        `/api/v1/workspace/browse${qs ? `?${qs}` : ""}`,
      );
    },
    enabled,
    staleTime: 15_000,
  });
}
