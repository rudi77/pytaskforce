# `src/theme/` — FluentUI v9 theme layer

Tracks issue [#438](https://github.com/rudi77/pytaskforce/issues/438).

## Files

- `brand.ts` — `taskforceBrand: BrandVariants` (the 16-step blue ramp).
- `themes.ts` — `lightTheme` / `darkTheme` derived via `createLightTheme` / `createDarkTheme`.
- `FluentThemeBridge.tsx` — wraps the tree in `<FluentProvider>` and picks the right theme from `useTheme()` (the shadcn-era ThemeProvider).

## Two token systems coexist during the migration

The shadcn → Fluent migration lands page-by-page (see issue #438 page order).
While that's in flight, **two token systems coexist** under the same React tree:

| System | Variables | Source | Consumed by |
|---|---|---|---|
| **shadcn-era** (legacy) | `--background`, `--foreground`, `--primary`, `--muted-foreground`, … (HSL triplets) | `src/app/globals.css` `:root` + `.dark` blocks | Tailwind utilities (`bg-card`, `text-foreground`, `border-border`, …) used by every file in `src/components/ui/` and the page files that haven't been migrated yet |
| **FluentUI v9** | `--colorBrandBackground`, `--colorNeutralBackground1`, `--colorNeutralForeground1`, … (full color strings) | `<FluentProvider>` injects these on its DOM root via Griffel | All `@fluentui/react-components` components; new code can read them as `var(--colorBrandBackground)` inside the provider tree |

They don't collide — different names. Until a real bridge is needed, both layers
just live next to each other. Pages that mix migrated + unmigrated components
may have minor brand-tone drift; that's accepted for the migration window.

## When the bridge becomes real

A token bridge becomes valuable as soon as:

- a non-Fluent component (e.g. recharts, react-flow, react-markdown) needs to
  follow Fluent's brand color automatically, or
- shadcn-era primitives stay alongside Fluent ones for a long time and the
  visual drift is too noticeable.

Add the bridge then — not before. The shape will probably be a small CSS
sidecar that re-declares a subset of the shadcn variables in terms of
`var(--colorBrandBackground)` / `var(--colorNeutralForeground1)` / etc., kept
small and explicit. Place it next to this README and load it after
`globals.css`.

## Brand tweaks

Edit `brand.ts` only. Every Fluent token (and any future bridge mapping) is
derived from that file.

The ramp follows Tailwind's `blue-*` scale to stay continuous with the
pre-Fluent UI (`#2563EB` → step 80 in light mode). If a different hue is
needed, generate a fresh 16-step ramp with
[Fluent's brand-color theme designer](https://fluent2.microsoft.design/components/web/react/theme/default)
and replace the contents of `taskforceBrand`.
