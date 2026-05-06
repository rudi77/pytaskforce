#!/usr/bin/env tsx
/**
 * OpenAPI codegen
 * ===============
 *
 * Reads the FastAPI OpenAPI document and writes a TypeScript schema file under
 * src/api/generated/schema.d.ts.
 *
 * Sources, in order of preference:
 *   1) HTTP — TASKFORCE_OPENAPI_URL env var (default http://127.0.0.1:8070/openapi.json)
 *   2) Python fallback — `python -c "from taskforce.api.server import app; print(app.openapi())"`
 *
 * Pass --check to fail when the generated file would change (CI drift gate).
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import openapiTS, { astToString } from "openapi-typescript";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const OUTPUT = resolve(ROOT, "src/api/generated/schema.d.ts");
const URL = process.env.TASKFORCE_OPENAPI_URL ?? "http://127.0.0.1:8070/openapi.json";

const CHECK = process.argv.includes("--check");

async function fetchSpec(): Promise<unknown> {
  try {
    const response = await fetch(URL);
    if (response.ok) return await response.json();
    console.warn(`HTTP ${response.status} from ${URL}; falling back to python.`);
  } catch (err) {
    console.warn(`Could not reach ${URL} (${(err as Error).message}); trying python fallback.`);
  }
  const SCRIPT = [
    "import json, sys",
    "from taskforce.api.server import app",
    "sys.stdout.write(json.dumps(app.openapi()))",
  ].join("\n");
  const repoRoot = resolve(ROOT, "..");
  // Write the dump script to a temp file so Windows cmd.exe doesn't mangle
  // the semicolons / quotes when spawnSync goes through a shell.
  const scratchDir = mkdtempSync(join(tmpdir(), "tf-openapi-"));
  const scriptPath = join(scratchDir, "dump_openapi.py");
  writeFileSync(scriptPath, SCRIPT, "utf-8");
  try {
    // Try uv-managed env first (covers a fresh `uv sync` setup), then bare python.
    const candidates: Array<{ cmd: string; args: string[] }> = [
      { cmd: "uv", args: ["run", "--quiet", "python", scriptPath] },
      { cmd: "python", args: [scriptPath] },
    ];
    let lastErr = "";
    for (const { cmd, args } of candidates) {
      const result = spawnSync(cmd, args, {
        encoding: "utf-8",
        cwd: repoRoot,
        shell: process.platform === "win32",
      });
      if (result.error) {
        lastErr = `${cmd}: ${result.error.message}`;
        continue;
      }
      if (result.status === 0 && result.stdout) {
        return JSON.parse(result.stdout);
      }
      lastErr = result.stderr || `${cmd} exited ${result.status}`;
    }
    console.error(lastErr);
    throw new Error("Could not obtain OpenAPI spec via HTTP or Python fallback.");
  } finally {
    rmSync(scratchDir, { recursive: true, force: true });
  }
}

async function main() {
  const spec = await fetchSpec();
  const ast = await openapiTS(spec as Parameters<typeof openapiTS>[0]);
  const next =
    "/* eslint-disable */\n" +
    "// THIS FILE IS GENERATED. Run `pnpm run generate-api` to refresh.\n" +
    astToString(ast);

  if (CHECK) {
    if (!existsSync(OUTPUT)) {
      console.error(`Missing ${OUTPUT}. Run "pnpm run generate-api".`);
      process.exit(1);
    }
    const current = await readFile(OUTPUT, "utf-8");
    if (current !== next) {
      console.error("OpenAPI client is out of date. Run `pnpm run generate-api` and commit.");
      process.exit(1);
    }
    console.log("OpenAPI client is up to date.");
    return;
  }

  await mkdir(dirname(OUTPUT), { recursive: true });
  await writeFile(OUTPUT, next, "utf-8");
  console.log(`Wrote ${OUTPUT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
