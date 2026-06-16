# `src/theme/` — FluentUI v9 theme layer

Tracks issue [#438](https://github.com/rudi77/pytaskforce/issues/438).

## Files

- `brand.ts` — `taskforceBrand: BrandVariants` (the 16-step blue ramp).
- `themes.ts` — `lightTheme` / `darkTheme`: derived via `createLightTheme` /
  `createDarkTheme`, **then overridden** with the design system's slate neutral
  ramp (Fluent ships a pure-grey neutral ramp; the override gives Fluent
  surfaces the brand's cool slate identity) and `fontFamilyBase`/`Monospace`.
- `FluentThemeBridge.tsx` — wraps the tree in `<FluentProvider>` and picks the
  right theme from `useTheme()`.
- Webfonts (Inter + JetBrains Mono) load via `<link>` in `ui/index.html`.

## Two token systems, kept value-identical (the bridge is real)

Two token systems live under the same React tree, but as of the 2026-06-16
re-skin they carry **the same slate values**, so Tailwind-styled and
Fluent-native components render an identical, on-brand surface.

| System | Variables | Source | Consumed by |
|---|---|---|---|
| **Tailwind tokens** | `--background`, `--foreground`, `--primary`, `--muted-foreground`, … (HSL triplets) | `src/app/globals.css` `:root` + `.dark` | Tailwind utilities (`bg-card`, `text-foreground`, `border-border`, …) used by `src/components/ui/*` styled-div primitives and the pages |
| **FluentUI v9** | `--colorNeutralBackground1`, `--colorNeutralForeground1`, `--colorBrandBackground`, … | `<FluentProvider>` (Griffel) from `themes.ts` | All `@fluentui/react-components` components |

The two are kept in sync by hand: `themes.ts` neutral overrides and the
`globals.css` slate values mirror each other (both source from the design
system's slate ramp + Tailwind `blue-*` brand). **Change them together.**

## Tweaks

- **Brand hue:** edit `brand.ts` only — every Fluent brand token derives from it.
  The ramp follows Tailwind `blue-*` (`#2563EB` → step 80 light).
- **Neutral/surface tone:** edit the `slate` ramp in `themes.ts` **and** the
  matching `--foreground` / `--muted` / `--border` / … HSL values in
  `globals.css` so the two systems stay identical.

> Design language: FluentUI v9 is the component layer; icons are
> `@fluentui/react-icons` app-wide. The `taskforce-design-system` skill's
> **color + type tokens are canonical** (restored here); its Lucide-only and
> component-recreation rules are superseded by Fluent.
