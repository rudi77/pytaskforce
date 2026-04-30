import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SettingsState {
  apiBaseUrl: string;
  apiToken: string;
  setApiBaseUrl: (value: string) => void;
  setApiToken: (value: string) => void;
}

const DEFAULT_API_BASE = "";

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      apiBaseUrl: DEFAULT_API_BASE,
      apiToken: "",
      setApiBaseUrl: (value) => set({ apiBaseUrl: value.trim() }),
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
