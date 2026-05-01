import type { AgentTemplate } from "@/api/queries";

export interface WizardState {
  template: AgentTemplate | null;
  /** Auto-derived from displayName, but editable in advanced mode. */
  name: string;
  displayName: string;
  description: string;
  emoji: string;
  /** Selected tool short-names. */
  tools: string[];
  tone: string;
  language: string;
  rules: string;
  systemPrompt: string;
  /** Whether the LLM-refine pass produced this prompt successfully. */
  promptUsedAI: boolean;
}

export const EMPTY_WIZARD_STATE: WizardState = {
  template: null,
  name: "",
  displayName: "",
  description: "",
  emoji: "✨",
  tools: [],
  tone: "professionell",
  language: "Deutsch",
  rules: "",
  systemPrompt: "",
  promptUsedAI: false,
};

export const TONE_OPTIONS = [
  { id: "professionell", label: "Professionell" },
  { id: "locker", label: "Locker" },
  { id: "formell", label: "Formell" },
] as const;

export const LANGUAGE_OPTIONS = [
  { id: "Deutsch", label: "Deutsch" },
  { id: "English", label: "English" },
  { id: "Français", label: "Français" },
] as const;

/** Convert a display name into a valid profile id (matches NAME_PATTERN). */
export function deriveProfileId(displayName: string): string {
  const slug = displayName
    .toLowerCase()
    .replace(/ß/g, "ss")
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
  return slug || "agent";
}
