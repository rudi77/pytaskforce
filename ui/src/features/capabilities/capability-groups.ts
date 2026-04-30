/**
 * Plain-language grouping of tools and skills used by both the wizard and
 * the unified Capabilities page.
 *
 * The backend stays as-is — tools/skills/MCP are still distinct concepts on
 * the server. This grouping is purely a UI-level abstraction so a non-technical
 * user sees "Office-Dokumente" instead of "docx, pptx, excel".
 *
 * If a tool short-name isn't listed here it falls into the "other" group, so
 * the file does not need to be exhaustive — but should cover the common ones.
 */

import type { ComponentType } from "react";
import {
  BookOpen,
  Briefcase,
  Brain,
  Code2,
  FileText,
  FolderOpen,
  Globe,
  Mail,
  Plug,
  ShieldAlert,
  Sparkles,
  Wrench,
} from "lucide-react";

export type CapabilityGroupId =
  | "files"
  | "office"
  | "web"
  | "communication"
  | "knowledge"
  | "code"
  | "domain"
  | "other";

export interface CapabilityGroup {
  id: CapabilityGroupId;
  label: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  tools: readonly string[];
}

export const CAPABILITY_GROUPS: readonly CapabilityGroup[] = [
  {
    id: "files",
    label: "Dateien lesen & schreiben",
    description: "Texte, Tabellen und Dokumente öffnen, ändern und speichern",
    icon: FolderOpen,
    tools: ["file_read", "file_write", "edit", "grep", "glob"],
  },
  {
    id: "office",
    label: "Office-Dokumente",
    description: "Word, Excel und PowerPoint bearbeiten",
    icon: FileText,
    tools: ["docx", "excel", "pptx"],
  },
  {
    id: "web",
    label: "Im Web recherchieren",
    description: "Google-Suche, Webseiten lesen, Browser-Automatisierung",
    icon: Globe,
    tools: ["web_search", "web_fetch", "browser"],
  },
  {
    id: "communication",
    label: "E-Mail, Kalender & Termine",
    description: "Mail lesen/schreiben, Termine, Erinnerungen (benötigt Butler)",
    icon: Mail,
    tools: [
      "gmail",
      "calendar",
      "schedule",
      "reminder",
      "google_drive",
      "send_notification",
    ],
  },
  {
    id: "knowledge",
    label: "Wissen merken",
    description: "Eigenes Wiki, Langzeit-Erinnerung, frühere Ergebnisse",
    icon: Brain,
    tools: ["wiki", "memory", "fetch_result"],
  },
  {
    id: "code",
    label: "Code & Skripte ausführen",
    description: "Python-Code, Shell, Git — erfordert oft Genehmigung",
    icon: Code2,
    tools: ["python", "bash", "shell", "powershell", "git", "github"],
  },
  {
    id: "domain",
    label: "Buchhaltung & Auditing",
    description: "Spezialwerkzeuge für Belege und Compliance",
    icon: Briefcase,
    tools: ["accounting_validate", "accounting_audit"],
  },
  {
    id: "other",
    label: "Weitere Werkzeuge",
    description: "Alles andere",
    icon: Wrench,
    tools: [],
  },
];

const TOOL_TO_GROUP: Record<string, CapabilityGroupId> = (() => {
  const map: Record<string, CapabilityGroupId> = {};
  for (const group of CAPABILITY_GROUPS) {
    for (const tool of group.tools) {
      map[tool] = group.id;
    }
  }
  return map;
})();

export function groupForTool(toolName: string): CapabilityGroupId {
  return TOOL_TO_GROUP[toolName] ?? "other";
}

/** Plain-language labels for individual tools (override the raw short name). */
const TOOL_LABELS: Record<string, string> = {
  file_read: "Datei lesen",
  file_write: "Datei schreiben",
  edit: "Datei bearbeiten",
  grep: "In Dateien suchen",
  glob: "Dateien finden",
  docx: "Word-Dokumente",
  excel: "Excel-Tabellen",
  pptx: "PowerPoint",
  web_search: "Websuche",
  web_fetch: "Webseite lesen",
  browser: "Browser-Automatisierung",
  gmail: "Gmail",
  calendar: "Kalender",
  schedule: "Termine",
  reminder: "Erinnerungen",
  google_drive: "Google Drive",
  send_notification: "Benachrichtigungen senden",
  wiki: "Eigenes Wiki",
  memory: "Erinnerung",
  fetch_result: "Frühere Ergebnisse",
  python: "Python ausführen",
  bash: "Bash-Befehle",
  shell: "Shell-Befehle",
  powershell: "PowerShell",
  git: "Git-Befehle",
  github: "GitHub",
  accounting_validate: "Belege prüfen",
  accounting_audit: "Audit",
  ask_user: "Nachfragen",
  llm: "Zweite KI-Stimme",
  multimedia: "Bilder & Medien",
  activate_skill: "Skills aktivieren",
};

export function labelForTool(toolName: string): string {
  return TOOL_LABELS[toolName] ?? toolName;
}

/** Tools that should warn the user — they can do destructive things. */
const HIGH_RISK_TOOLS = new Set([
  "python",
  "bash",
  "shell",
  "powershell",
  "git",
  "github",
  "browser",
]);

export function isHighRiskTool(toolName: string): boolean {
  return HIGH_RISK_TOOLS.has(toolName);
}

export const CAPABILITY_KIND_META = {
  tool: { label: "Werkzeug", icon: Wrench },
  skill: { label: "Workflow", icon: Sparkles },
  mcp: { label: "Verbindung", icon: Plug },
  warning: { label: "Erweitert", icon: ShieldAlert },
  knowledge: { label: "Wissen", icon: BookOpen },
} as const;
