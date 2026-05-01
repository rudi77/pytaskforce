import { describe, expect, it } from "vitest";

import {
  CAPABILITY_GROUPS,
  groupForSkill,
  groupForTool,
  isHighRiskTool,
  labelForTool,
} from "./capability-groups";

describe("capability-groups", () => {
  it("maps known tools to their semantic group", () => {
    expect(groupForTool("file_read")).toBe("files");
    expect(groupForTool("docx")).toBe("office");
    expect(groupForTool("excel")).toBe("office");
    expect(groupForTool("web_search")).toBe("web");
    expect(groupForTool("gmail")).toBe("communication");
    expect(groupForTool("wiki")).toBe("knowledge");
    expect(groupForTool("python")).toBe("code");
  });

  it("falls back to 'other' for unknown tools", () => {
    expect(groupForTool("totally-made-up")).toBe("other");
    expect(groupForTool("")).toBe("other");
  });

  it("flags shell-level tools as high risk", () => {
    expect(isHighRiskTool("python")).toBe(true);
    expect(isHighRiskTool("bash")).toBe(true);
    expect(isHighRiskTool("shell")).toBe(true);
    expect(isHighRiskTool("powershell")).toBe(true);
    expect(isHighRiskTool("git")).toBe(true);
    expect(isHighRiskTool("github")).toBe(true);
    expect(isHighRiskTool("browser")).toBe(true);
  });

  it("does NOT flag safe tools as high risk", () => {
    expect(isHighRiskTool("file_read")).toBe(false);
    expect(isHighRiskTool("wiki")).toBe(false);
    expect(isHighRiskTool("ask_user")).toBe(false);
    expect(isHighRiskTool("docx")).toBe(false);
  });

  it("provides plain-language labels", () => {
    expect(labelForTool("file_read")).toBe("Datei lesen");
    expect(labelForTool("excel")).toBe("Excel-Tabellen");
    expect(labelForTool("python")).toBe("Python ausführen");
  });

  it("falls back to the raw name when no label is registered", () => {
    expect(labelForTool("custom_unknown_tool")).toBe("custom_unknown_tool");
  });

  it("each declared group has a non-empty label and description", () => {
    for (const group of CAPABILITY_GROUPS) {
      expect(group.label.length).toBeGreaterThan(0);
      expect(group.description.length).toBeGreaterThan(0);
    }
  });

  it("does not classify the same tool into multiple groups", () => {
    const seen = new Map<string, string>();
    for (const group of CAPABILITY_GROUPS) {
      for (const tool of group.tools) {
        const prev = seen.get(tool);
        if (prev) {
          throw new Error(
            `Tool '${tool}' assigned to both '${prev}' and '${group.id}'`,
          );
        }
        seen.set(tool, group.id);
      }
    }
  });
});

describe("groupForSkill", () => {
  it("routes code-related skills to the code group", () => {
    expect(groupForSkill("code-review", "context")).toBe("code");
    expect(groupForSkill("test-runner", "context")).toBe("code");
  });

  it("routes office-related skills to the office group", () => {
    expect(groupForSkill("pdf-processing", "library")).toBe("office");
    expect(groupForSkill("docx-extract", "library")).toBe("office");
  });

  it("routes communication skills to the communication group", () => {
    expect(groupForSkill("mail-formatter", "context")).toBe("communication");
    expect(groupForSkill("calendar-helper", "context")).toBe("communication");
  });

  it("routes 'agent' type skills to the domain group", () => {
    expect(groupForSkill("anything", "agent")).toBe("domain");
  });

  it("falls back to 'knowledge' for everything else", () => {
    expect(groupForSkill("misc-skill", "context")).toBe("knowledge");
  });
});
