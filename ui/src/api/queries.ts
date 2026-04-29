import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";

export interface HealthResponse {
  status: string;
  version?: string;
  checks?: Record<string, unknown>;
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
}

export interface ConversationSummary {
  conversation_id: string;
  topic: string;
  summary: string;
  started_at: string;
  archived_at: string;
  message_count: number;
}

export interface ChatMessage {
  role: string;
  content: string;
  attachments?: FileMetadata[];
}

export const queryKeys = {
  health: ["health"] as const,
  agents: ["agents", "list"] as const,
  agent: (id: string) => ["agents", "detail", id] as const,
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
  archivedConversations: ["conversations", "archived"] as const,
  conversationMessages: (id: string) => ["conversations", "messages", id] as const,
};

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
  });
}

export function useSkills() {
  return useQuery<{ skills: SkillSummary[] }>({
    queryKey: queryKeys.skills,
    queryFn: () => apiFetch<{ skills: SkillSummary[] }>("/api/v1/skills"),
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

export function useConversations() {
  return useQuery<ConversationInfo[]>({
    queryKey: queryKeys.conversations,
    queryFn: () => apiFetch<ConversationInfo[]>("/api/v1/conversations"),
  });
}

export function useArchivedConversations(limit = 20) {
  return useQuery<ConversationSummary[]>({
    queryKey: queryKeys.archivedConversations,
    queryFn: () =>
      apiFetch<ConversationSummary[]>("/api/v1/conversations/archived", {
        query: { limit },
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
