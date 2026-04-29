# Taskforce Management UI

React + TypeScript front-end for the Taskforce framework. Built with Vite,
Tailwind, and shadcn/ui-style primitives. Talks to the existing FastAPI backend
in `src/taskforce/api/`.

## Prerequisites

- Node 20+
- pnpm (or npm/yarn — but lockfile assumes pnpm)
- A running Taskforce backend on `http://127.0.0.1:8070` for development

## Getting started

```bash
cd ui
pnpm install
pnpm run dev
```

The dev server starts on http://localhost:5173 and proxies `/api/...` and
`/health` to the backend (override with `TASKFORCE_API_URL` if it lives
elsewhere).

In production builds you can point the UI at any backend through the **Settings
page** — the `apiBaseUrl` is persisted in `localStorage`.

## Useful scripts

| Command | What it does |
| ------- | ------------ |
| `pnpm run dev` | Vite dev server with HMR + API proxy |
| `pnpm run build` | Type-check (`tsc -b`) + production build into `dist/` |
| `pnpm run preview` | Serve the production build locally |
| `pnpm run typecheck` | Type-check only |
| `pnpm run generate-api` | Refresh `src/api/generated/schema.d.ts` from `/openapi.json` |
| `pnpm run generate-api:check` | Fail if the generated client is out of date (CI drift gate) |

## Project layout

```
src/
  api/            HTTP client, query hooks, generated OpenAPI types
  app/            Router, AppShell, theme provider, global CSS
  components/ui/  Reusable primitives (button, card, input, badge, …)
  components/     App-specific shared components (HealthIndicator, …)
  features/       Feature slices — agents/, chat/, monitoring/, acp/ (added per phase)
  lib/            Utilities (cn helper, settings store)
  pages/          One file per route
```

## Backend expectations

The UI assumes the FastAPI app exposes:

- `GET /health`, `GET /health/ready`
- `GET /openapi.json` (used by `generate-api`)
- CORS enabled — set `CORS_ORIGINS=http://localhost:5173` (or `*`) on the backend

Newer endpoints are added phase by phase per the implementation plan in
`.claude/plans/`.

## Theme

Tailwind `darkMode: "class"`. Theme preference (`light` / `dark` / `system`) is
persisted in `localStorage` under `taskforce.theme`. An inline script in
`index.html` applies the right class before React hydrates so there is no flash
of the wrong theme.
