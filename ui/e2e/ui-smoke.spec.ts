import { expect, test, type Page } from "@playwright/test";

const agents = [
  {
    source: "profile",
    profile: "default",
    specialist: null,
    tools: [],
    mcp_servers: [],
    llm: {},
    persistence: {},
  },
  {
    source: "profile",
    profile: "butler",
    specialist: "butler",
    tools: [],
    mcp_servers: [],
    llm: {},
    persistence: {},
  },
  {
    source: "profile",
    profile: "rag_agent",
    specialist: "rag",
    tools: [],
    mcp_servers: [],
    llm: {},
    persistence: {},
  },
  {
    source: "plugin",
    agent_id: "document_extraction_agent",
    name: "Document Extraction Agent",
    description: "Extracts structured data from documents.",
    plugin_path: "plugins/document_extraction_agent",
    tool_classes: [],
    specialist: null,
    mcp_servers: [],
  },
];

const accountantAssistantName = "Buchhalter DACH Assistant";
const accountantAssistantSlug = "buchhalter-dach-assistant";
const accountantAssistantDescription =
  "Übernimmt die vorbereitende Buchhaltung für Kleinunternehmen im DACH-Raum: Belege prüfen, Rechnungen erfassen, Buchungsvorschläge vorbereiten und USt-/MwSt.-Sachverhalte strukturiert für die Steuerberatung aufbereiten.";
const accountantAssistantRules = [
  "Arbeite nach DACH-Kontext: Deutschland, Österreich und Schweiz klar unterscheiden.",
  "Keine Rechts- oder Steuerberatung vortäuschen; bei Unsicherheit an Steuerberater oder Treuhänder verweisen.",
  "Beträge, Währungen, Steuersätze und Belegdatum immer explizit prüfen.",
  "Fehlende Pflichtangaben bei Rechnungen und Belegen aktiv benennen.",
].join("\n");
const accountantAssistantPrompt =
  "Du bist ein Buchhalter-Assistent für Kleinunternehmen im DACH-Raum.\n\n" +
  "Du unterstützt bei vorbereitender Buchhaltung, Belegprüfung, Rechnungsprüfung, Buchungsvorschlägen, Umsatzsteuer-/Mehrwertsteuer-Einordnung und sauberer Übergabe an Steuerberatung oder Treuhand.\n\n" +
  `Aufgabe:\n${accountantAssistantDescription}\n\n` +
  `Verbindliche Regeln:\n${accountantAssistantRules}`;

const profiles = [
  {
    name: "default",
    path: "src/taskforce/configs/default.yaml",
    format: "yaml",
    description: "Default agent profile",
    specialist: null,
    name_label: null,
    is_custom: false,
  },
  {
    name: "butler",
    path: "agents/butler/configs/butler.yaml",
    format: "yaml",
    description: "Personal assistant",
    specialist: "butler",
    name_label: "Butler",
    is_custom: false,
  },
];

const tools = [
  {
    name: "wiki",
    description: "Personal wiki for long-term memory.",
    parameters_schema: {
      type: "object",
      properties: { query: { type: "string" } },
    },
    requires_approval: false,
    approval_risk_level: "low",
  },
  {
    name: "file_read",
    description: "Read files from the local workspace.",
    parameters_schema: { type: "object", properties: {} },
    requires_approval: false,
    approval_risk_level: "low",
  },
  {
    name: "file_write",
    description: "Write generated accounting summaries to files.",
    parameters_schema: { type: "object", properties: {} },
    requires_approval: true,
    approval_risk_level: "medium",
  },
  {
    name: "excel",
    description: "Read and write spreadsheet-based accounting exports.",
    parameters_schema: { type: "object", properties: {} },
    requires_approval: false,
    approval_risk_level: "low",
  },
  {
    name: "docx",
    description: "Create Word summaries for handoff to tax advisors.",
    parameters_schema: { type: "object", properties: {} },
    requires_approval: false,
    approval_risk_level: "low",
  },
  {
    name: "accounting_validate",
    description: "Validate invoice and bookkeeping data.",
    parameters_schema: { type: "object", properties: {} },
    requires_approval: false,
    approval_risk_level: "low",
  },
  {
    name: "ask_user",
    description: "Ask the user for missing accounting context.",
    parameters_schema: { type: "object", properties: {} },
    requires_approval: false,
    approval_risk_level: "low",
  },
  {
    name: "edit",
    description: "Perform exact string replacements in files.",
    parameters_schema: { type: "object", properties: {} },
    requires_approval: true,
    approval_risk_level: "high",
  },
];

const conversations = [
  {
    conversation_id: "conv-rest",
    channel: "rest",
    started_at: "2026-05-02T10:00:00Z",
    last_activity: "2026-05-02T10:05:00Z",
    message_count: 2,
    topic: "rest",
  },
];

async function mockTaskforceApi(page: Page) {
  let createdProfile:
    | {
        name: string;
        config: Record<string, unknown>;
        yaml_text: string;
      }
    | null = null;

  await page.route("**/health", (route) =>
    route.fulfill({ json: { status: "ok", version: "test" } }),
  );
  await page.route("**/api/v1/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/api/v1/agents") {
      const createdAgent = createdProfile
        ? [
            {
              source: "profile",
              profile: createdProfile.name,
              specialist: null,
              tools: (createdProfile.config.tools as string[]) ?? [],
              mcp_servers: [],
              llm: {},
              persistence: {},
            },
          ]
        : [];
      return route.fulfill({ json: { agents: [...agents, ...createdAgent] } });
    }
    if (path === "/api/v1/profiles" && route.request().method() === "POST") {
      const payload = route.request().postDataJSON() as {
        name: string;
        config: Record<string, unknown>;
      };
      createdProfile = {
        name: payload.name,
        config: payload.config,
        yaml_text: `profile: ${payload.name}\n`,
      };
      return route.fulfill({
        json: {
          name: payload.name,
          path: `custom/${payload.name}.yaml`,
          format: "yaml",
          description: String(payload.config.description ?? ""),
          specialist: null,
          is_writable: true,
          config: payload.config,
          yaml_text: createdProfile.yaml_text,
        },
      });
    }
    if (path === "/api/v1/profiles") {
      const createdSummary = createdProfile
        ? [
            {
              name: createdProfile.name,
              path: `custom/${createdProfile.name}.yaml`,
              format: "yaml",
              description: String(createdProfile.config.description ?? ""),
              specialist: null,
              name_label:
                typeof createdProfile.config.agent === "object" &&
                createdProfile.config.agent !== null
                  ? String((createdProfile.config.agent as { name?: unknown }).name ?? "")
                  : null,
              is_custom: true,
            },
          ]
        : [];
      return route.fulfill({ json: { profiles: [...profiles, ...createdSummary] } });
    }
    if (path === "/api/v1/profiles/default") {
      return route.fulfill({
        json: {
          ...profiles[0],
          config: { profile: "default", tools: ["wiki", "file_read"] },
          yaml_text: "profile: default\ntools:\n  - wiki\n  - file_read\n",
        },
      });
    }
    if (path === "/api/v1/profiles/butler") {
      return route.fulfill({
        json: {
          ...profiles[1],
          config: { profile: "butler", specialist: "butler", tools: ["wiki"] },
          yaml_text: "profile: butler\nspecialist: butler\ntools:\n  - wiki\n",
        },
      });
    }
    if (path === `/api/v1/profiles/${accountantAssistantSlug}` && createdProfile) {
      return route.fulfill({
        json: {
          name: createdProfile.name,
          path: `custom/${createdProfile.name}.yaml`,
          format: "yaml",
          description: String(createdProfile.config.description ?? ""),
          specialist: null,
          is_writable: true,
          config: createdProfile.config,
          yaml_text: createdProfile.yaml_text,
        },
      });
    }
    if (path === "/api/v1/profiles/available-as-subagent") {
      return route.fulfill({ json: { profiles } });
    }
    if (path === "/api/v1/tools") {
      return route.fulfill({ json: { tools } });
    }
    if (path === "/api/v1/skills") {
      return route.fulfill({
        json: {
          skills: [
            {
              name: "code-review",
              description: "Review source code changes.",
              skill_type: "context",
              slash_name: "code-review",
              file_path: ".taskforce/skills/code-review/SKILL.md",
              allowed_tools: ["file_read"],
            },
          ],
        },
      });
    }
    if (path === "/api/v1/skills/code-review") {
      return route.fulfill({
        json: {
          name: "code-review",
          description: "Review source code changes.",
          skill_type: "context",
          slash_name: "code-review",
          file_path: ".taskforce/skills/code-review/SKILL.md",
          allowed_tools: ["file_read"],
          body: "Review changes and report risks first.",
        },
      });
    }
    if (path === "/api/v1/agent-templates") {
      return route.fulfill({
        json: {
          templates: [
            {
              id: "accounting",
              name: "Buchhalter-Assistent",
              description:
                "Hilft beim Erfassen von Belegen, Buchungssätzen und einfachen Buchhaltungsfragen.",
              emoji: "🧾",
              persona_hint:
                "Beschreibe, welche Buchhaltungsaufgaben der Agent für dein Kleinunternehmen übernehmen soll.",
              recommended_tools: [
                "file_read",
                "file_write",
                "excel",
                "docx",
                "accounting_validate",
                "ask_user",
                "wiki",
              ],
              recommended_skills: [],
              system_prompt_template:
                "Du bist ein sorgfältiger Buchhalter-Assistent für Kleinunternehmen.",
              example_prompts: [
                "Prüfe diese Eingangsrechnung auf fehlende Pflichtangaben.",
                "Bereite eine Monatsübersicht für die Steuerberatung vor.",
              ],
              tone_default: "professionell",
              language_default: "Deutsch",
            },
            {
              id: "research",
              name: "Recherche-Assistent",
              description: "Sucht im Web und fasst Quellen zusammen.",
              emoji: "🔎",
              persona_hint: "Research assistant",
              recommended_tools: ["web_search", "web_fetch", "wiki"],
              recommended_skills: [],
              system_prompt_template: "You are a research assistant.",
              example_prompts: [],
              tone_default: "präzise",
              language_default: "Deutsch",
            },
          ],
        },
      });
    }
    if (path === "/api/v1/agent-templates/compose-prompt") {
      return route.fulfill({
        json: {
          system_prompt: accountantAssistantPrompt,
          used_ai: false,
          ai_attempted: false,
          ai_error: null,
        },
      });
    }
    if (path === "/api/v1/planning-strategies") {
      return route.fulfill({ json: { strategies: [] } });
    }
    if (path === "/api/v1/llm/models") {
      return route.fulfill({ json: { default_model: "main", models: [] } });
    }
    if (path === "/api/v1/conversations") {
      return route.fulfill({ json: conversations });
    }
    if (path === "/api/v1/conversations/archived") {
      return route.fulfill({ json: [] });
    }
    if (path === "/api/v1/conversations/conv-rest/messages") {
      return route.fulfill({
        json: [
          { role: "user", content: "Wer bist du?" },
          { role: "assistant", content: "Ich bin dein Taskforce Agent." },
        ],
      });
    }
    if (path === "/api/v1/analytics/token-usage") {
      return route.fulfill({
        json: {
          granularity: url.searchParams.get("granularity") ?? "hour",
          pricing_as_of: "2026-04-29",
          buckets: [
            {
              bucket: "2026-05-02T10:00:00Z",
              prompt_tokens: 1200,
              completion_tokens: 300,
              total_tokens: 1500,
              cost_usd: 0.01,
              call_count: 2,
            },
          ],
        },
      });
    }
    if (path === "/api/v1/analytics/cost-summary") {
      return route.fulfill({
        json: {
          today_usd: 0.019,
          week_usd: 0.019,
          month_usd: 0.019,
          pricing_as_of: "2026-04-29",
          by_agent: [
            {
              agent: "default",
              prompt_tokens: 1200,
              completion_tokens: 300,
              total_tokens: 1500,
              cost_usd: 0.019,
            },
          ],
          by_model: [
            {
              model: "gpt-5.4-mini",
              prompt_tokens: 1200,
              completion_tokens: 300,
              total_tokens: 1500,
              cost_usd: 0.019,
            },
          ],
        },
      });
    }
    if (path === "/api/v1/runs/active") {
      return route.fulfill({ json: { runs: [] } });
    }
    if (path === "/api/v1/runs/recent") {
      return route.fulfill({
        json: {
          runs: [
            {
              session_id: "run-1",
              started_at: "2026-05-02T10:00:00Z",
              profile: "default",
              agent_id: null,
              mission_preview: "Wer bist du?",
              finished: true,
              final_status: "completed",
              event_count: 2,
              total_prompt_tokens: 1200,
              total_completion_tokens: 300,
              total_cost_usd: 0.019,
            },
          ],
        },
      });
    }
    if (path === "/api/v1/acp/peers") {
      return route.fulfill({ json: [] });
    }
    if (path === "/api/v1/evals/runs") {
      return route.fulfill({ json: { runs: [] } });
    }

    return route.fulfill({ status: 404, json: { message: `Unhandled test route: ${path}` } });
  });
}

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (text.includes("React Router Future Flag Warning")) {
      return;
    }
    if (message.type() === "error") {
      errors.push(text);
    }
  });
  return errors;
}

test.beforeEach(async ({ page }) => {
  await mockTaskforceApi(page);
});

test("navigates dashboard, agents, monitoring, and capabilities", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Tokens today")).toBeVisible();

  await page.getByRole("link", { name: "Agents" }).click();
  await page.getByPlaceholder("Search agents…").fill("rag");
  await expect(page.getByRole("link", { name: /rag_agent/ })).toBeVisible();
  await page.getByPlaceholder("Search agents…").fill("");
  await page.getByRole("button", { name: /Plugin/ }).click();
  await expect(page.getByRole("link", { name: /Document Extraction Agent/ })).toBeVisible();

  await page.getByRole("link", { name: "Monitoring" }).click();
  await expect(page.getByRole("heading", { name: "Monitoring" }).first()).toBeVisible();
  await page.getByRole("button", { name: "7 days" }).click();
  await expect(page.getByText("Stacked prompt vs. completion · day-buckets")).toBeVisible();

  await page.getByRole("link", { name: "Fähigkeiten" }).click();
  await page.getByPlaceholder("Suchen…").fill("wiki");
  await page.getByRole("button", { name: /Eigenes Wiki/ }).click();
  await expect(page.getByRole("heading", { name: "wiki" })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});

test("opens an existing conversation and keeps the composer usable", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);

  await page.goto("/chat");
  await page.getByRole("link", { name: /rest/ }).click();
  await expect(page.getByRole("heading", { name: /Conversation conv-rest/ })).toBeVisible();
  await expect(page.getByText("Ich bin dein Taskforce Agent.")).toBeVisible();

  const composer = page.getByPlaceholder("Ask the agent… (drag files in or paste images)");
  await composer.fill("UI smoke test draft");
  await expect(composer).toHaveValue("UI smoke test draft");
  await composer.fill("");
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});

test("checks the agent wizard and profile comparison flow", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);

  await page.goto("/agents/new");
  await page.getByRole("button", { name: /Recherche-Assistent/ }).click();
  await page.getByRole("button", { name: "Weiter" }).click();
  await page.getByLabel("Wie soll dein Agent heißen?").fill("Recherche Test Agent");
  await expect(page.getByText("recherche-test-agent")).toBeVisible();

  await page.goto("/agents/compare");
  await page.getByLabel(/Left/).selectOption("default");
  await page.getByLabel(/Right/).selectOption("butler");
  await expect(page.getByRole("heading", { name: "default ↔ butler" })).toBeVisible();
  await expect(page.getByText(/\+\d+ additions/)).toBeVisible();

  expect(consoleErrors).toEqual([]);
});

test("creates a DACH bookkeeping assistant through the complete new-agent wizard", async ({
  page,
}) => {
  const consoleErrors = collectConsoleErrors(page);
  let createPayload:
    | {
        name: string;
        config: {
          description?: string;
          system_prompt?: string;
          tools?: string[];
          agent?: { name?: string; planning_strategy?: string; max_steps?: number };
        };
      }
    | null = null;

  page.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() === "POST" && url.pathname === "/api/v1/profiles") {
      createPayload = request.postDataJSON();
    }
  });

  await page.goto("/agents/new");
  await page.getByRole("button", { name: /Buchhalter-Assistent/ }).click();
  await page.getByRole("button", { name: "Weiter" }).click();

  await page.getByLabel("Wie soll dein Agent heißen?").fill(accountantAssistantName);
  await expect(page.getByText(accountantAssistantSlug)).toBeVisible();
  await page.getByLabel("Was soll er für dich tun?").fill(accountantAssistantDescription);
  await page.getByRole("button", { name: "Weiter" }).click();

  await expect(page.getByText(/Werkzeuge vorausgewählt/)).toBeVisible();
  await expect(page.getByLabel(/Datei lesen/)).toBeChecked();
  await expect(page.getByLabel(/Excel-Tabellen/)).toBeChecked();
  await expect(page.getByLabel(/Eigenes Wiki/)).toBeChecked();
  await page.getByRole("button", { name: "Weiter" }).click();

  await page.getByLabel("Wichtige Regeln (optional)").fill(accountantAssistantRules);
  await page.getByRole("button", { name: /Prompt neu erzeugen|Prompt erzeugen/ }).click();
  await expect(page.getByRole("textbox", { name: /Prompt erzeugen/ })).toHaveValue(
    /Du bist ein Buchhalter-Assistent/,
  );
  await page.getByRole("button", { name: "Weiter" }).click();

  await expect(page.getByText(accountantAssistantName).first()).toBeVisible();
  await expect(page.getByText(accountantAssistantSlug).first()).toBeVisible();
  await expect(page.getByText("Ausgewählte Werkzeuge (7)")).toBeVisible();
  await expect(page.getByText("DACH-Raum").first()).toBeVisible();

  await page.getByRole("button", { name: "Anlegen" }).click();
  await expect(page).toHaveURL(new RegExp(`/agents/${accountantAssistantSlug}$`));

  expect(createPayload).not.toBeNull();
  expect(createPayload?.name).toBe(accountantAssistantSlug);
  expect(createPayload?.config.agent?.name).toBe(accountantAssistantName);
  expect(createPayload?.config.description).toBe(accountantAssistantDescription);
  expect(createPayload?.config.system_prompt).toContain("DACH-Raum");
  expect(createPayload?.config.system_prompt).toContain("Kleinunternehmen");
  expect(createPayload?.config.tools).toEqual(
    expect.arrayContaining([
      "file_read",
      "file_write",
      "excel",
      "docx",
      "accounting_validate",
      "ask_user",
      "wiki",
    ]),
  );

  expect(consoleErrors).toEqual([]);
});

test("checks ACP, evals, and settings forms without persisting data", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);

  await page.goto("/acp");
  await expect(page.getByText("No peers registered")).toBeVisible();
  await page.getByRole("button", { name: "Add peer" }).first().click();
  await expect(page.getByRole("heading", { name: "Register ACP peer" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();

  await page.goto("/evals");
  await expect(page.getByRole("button", { name: "Run comparison" })).toBeDisabled();
  await page.getByRole("button", { name: "default" }).click();
  await expect(page.getByRole("button", { name: "Run comparison" })).toBeEnabled();

  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Dark" })).toBeVisible();
  await expect(page.getByLabel("API base URL")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
