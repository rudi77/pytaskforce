import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * View modes mirror Claude Code Desktop's "Transcript view" dropdown so
 * users get a familiar mental model:
 *
 *   - normal:  tool calls collapsed into summaries, full assistant text
 *   - verbose: every tool call + intermediate step expanded by default
 *   - summary: only the assistant's final responses (tool calls hidden)
 *
 * The setting is global (not per-conversation) because users tend to pick
 * one mode and stick with it; per-conversation overrides can be added
 * later if real usage shows the global default isn't enough.
 */
export type ChatViewMode = "normal" | "verbose" | "summary";

export const CHAT_VIEW_MODES: { value: ChatViewMode; label: string; hint: string }[] = [
  { value: "normal", label: "Normal", hint: "Tool calls collapsed" },
  { value: "verbose", label: "Verbose", hint: "All tool calls expanded" },
  { value: "summary", label: "Summary", hint: "Final responses only" },
];

interface ChatPreferencesState {
  viewMode: ChatViewMode;
  setViewMode: (mode: ChatViewMode) => void;
}

export const useChatPreferences = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      viewMode: "normal",
      setViewMode: (mode) => set({ viewMode: mode }),
    }),
    { name: "taskforce.chat.preferences" },
  ),
);
