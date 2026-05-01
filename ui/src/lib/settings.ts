import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SettingsState {
  apiBaseUrl: string;
  apiToken: string;
  /** Last validation error from setApiBaseUrl (empty when ok). */
  apiBaseUrlError: string;
  setApiBaseUrl: (value: string) => void;
  setApiToken: (value: string) => void;
}

const DEFAULT_API_BASE = "";

/**
 * Validate a base URL. Empty string is valid (means "use the same origin
 * via Vite's dev proxy"). Anything else must parse as http(s)://host.
 */
export function validateApiBaseUrl(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "Nur http:// oder https:// URLs sind erlaubt.";
    }
    return "";
  } catch {
    return "Keine gültige URL.";
  }
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      apiBaseUrl: DEFAULT_API_BASE,
      apiToken: "",
      apiBaseUrlError: "",
      setApiBaseUrl: (value) => {
        const trimmed = value.trim();
        const error = validateApiBaseUrl(trimmed);
        // Persist the value either way so the user sees what they typed,
        // but also surface the validation error for the UI to render.
        set({ apiBaseUrl: trimmed, apiBaseUrlError: error });
      },
      setApiToken: (value) => set({ apiToken: value.trim() }),
    }),
    { name: "taskforce.settings" },
  ),
);

export function getApiBaseUrl(): string {
  return useSettings.getState().apiBaseUrl || DEFAULT_API_BASE;
}

export function getApiToken(): string {
  return useSettings.getState().apiToken;
}
