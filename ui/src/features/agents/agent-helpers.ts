import type { AgentSummary } from "@/api/queries";

export function getAgentId(agent: AgentSummary): string {
  return agent.source === "profile" ? agent.profile : agent.agent_id;
}

export function getAgentName(agent: AgentSummary): string {
  if (agent.source === "profile") return agent.profile;
  return agent.name;
}

export function getAgentDescription(agent: AgentSummary): string {
  if (agent.source === "profile") {
    return agent.specialist ? `Specialist: ${agent.specialist}` : "Profile-based agent";
  }
  return agent.description;
}

export function getAgentTools(agent: AgentSummary): string[] {
  if (agent.source === "custom") return agent.tool_allowlist ?? [];
  if (agent.source === "plugin") return agent.tool_classes ?? [];
  return (agent.tools ?? []).map((t) => (typeof t === "string" ? t : JSON.stringify(t)));
}
