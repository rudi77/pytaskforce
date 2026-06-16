import {
  createDarkTheme,
  createLightTheme,
  type Theme,
} from "@fluentui/react-components";

import { taskforceBrand } from "./brand";

/**
 * FluentUI v9 themes for Taskforce.
 *
 * `lightTheme` and `darkTheme` are derived from `taskforceBrand` and consumed
 * by `<FluentProvider>` in `src/main.tsx` via `FluentThemeBridge`.
 *
 * Fluent's `createLightTheme`/`createDarkTheme` only take the brand ramp; the
 * neutral ramp it ships is a pure grey scale. That pure grey is what made the
 * UI read as "generic" rather than Taskforce. We override the high-traffic
 * neutral tokens with the design system's **slate-tinted** ramp so every Fluent
 * surface (backgrounds, text, strokes) carries the brand's cool slate identity.
 * The values mirror the slate tokens in `globals.css` and the design-system
 * skill (`taskforce-design-system/colors_and_type.css`), so Fluent-native and
 * Tailwind-styled components stay visually identical.
 */

// Tailwind `slate-*` ramp — the source of the design system's HSL neutrals.
const slate = {
  50: "#f8fafc",
  100: "#f1f5f9",
  200: "#e2e8f0",
  300: "#cbd5e1",
  400: "#94a3b8",
  500: "#64748b",
  600: "#475569",
  700: "#334155",
  800: "#1e293b",
  900: "#0f172a",
  950: "#020617",
} as const;

// Inter / JetBrains Mono are loaded as webfonts in index.html.
const fontFamilyBase =
  '"Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const fontFamilyMonospace =
  '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

const fontOverrides: Partial<Theme> = {
  fontFamilyBase,
  fontFamilyMonospace,
};

// Light: white canvas, slate text + strokes, slate-50/100 raised surfaces.
const lightNeutral: Partial<Theme> = {
  colorNeutralForeground1: slate[900],
  colorNeutralForeground2: slate[700],
  colorNeutralForeground3: slate[500],
  colorNeutralForeground4: slate[400],
  colorNeutralBackground1: "#ffffff",
  colorNeutralBackground1Hover: slate[50],
  colorNeutralBackground1Pressed: slate[100],
  colorNeutralBackground1Selected: slate[100],
  colorNeutralBackground2: slate[50],
  colorNeutralBackground3: slate[100],
  colorNeutralBackground4: slate[100],
  colorSubtleBackgroundHover: slate[100],
  colorSubtleBackgroundPressed: slate[200],
  colorSubtleBackgroundSelected: slate[100],
  colorNeutralStroke1: slate[300],
  colorNeutralStroke2: slate[200],
  colorNeutralStroke3: slate[100],
  colorNeutralStrokeAccessible: slate[500],
};

// Dark: deep slate canvas (222 47% 6%), raised slate surfaces, slate-50 text.
const darkCanvas = "#0a0f1a";
const darkBase = "#0f1623";
const darkNeutral: Partial<Theme> = {
  colorNeutralForeground1: slate[50],
  colorNeutralForeground2: slate[300],
  colorNeutralForeground3: slate[400],
  colorNeutralForeground4: slate[500],
  colorNeutralBackground1: darkBase,
  colorNeutralBackground1Hover: slate[800],
  colorNeutralBackground1Pressed: darkCanvas,
  colorNeutralBackground1Selected: slate[800],
  colorNeutralBackground2: darkCanvas,
  colorNeutralBackground3: slate[800],
  colorNeutralBackground4: slate[800],
  colorSubtleBackgroundHover: slate[800],
  colorSubtleBackgroundPressed: slate[700],
  colorSubtleBackgroundSelected: slate[800],
  colorNeutralStroke1: slate[800],
  colorNeutralStroke2: slate[800],
  colorNeutralStroke3: darkBase,
  colorNeutralStrokeAccessible: slate[400],
};

export const lightTheme: Theme = {
  ...createLightTheme(taskforceBrand),
  ...lightNeutral,
  ...fontOverrides,
};

export const darkTheme: Theme = {
  ...createDarkTheme(taskforceBrand),
  ...darkNeutral,
  ...fontOverrides,
};
