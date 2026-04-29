import { Badge } from "@/components/ui/badge";
import type { AgentSummary } from "@/api/queries";

const LABELS: Record<AgentSummary["source"], string> = {
  custom: "Custom",
  profile: "Profile",
  plugin: "Plugin",
};

const VARIANTS: Record<AgentSummary["source"], "default" | "secondary" | "outline"> = {
  custom: "default",
  profile: "secondary",
  plugin: "outline",
};

export function AgentSourceBadge({ source }: { source: AgentSummary["source"] }) {
  return <Badge variant={VARIANTS[source]}>{LABELS[source]}</Badge>;
}
