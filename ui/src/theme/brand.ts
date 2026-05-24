import type { BrandVariants } from "@fluentui/react-components";

/**
 * Brand ramp for the Taskforce FluentUI v9 theme.
 *
 * The ramp follows Tailwind's `blue-*` scale (the source of the previous
 * shadcn primary `#2563EB` and dark primary `#3B82F6`) so the visual identity
 * stays continuous with the pre-Fluent UI. FluentUI's `createLightTheme`
 * picks step 80 as the brand color in light mode; `createDarkTheme` picks
 * step 100 in dark mode.
 *
 * If a hue tweak is needed later, edit this file only — every Fluent token
 * downstream derives from it.
 */
export const taskforceBrand: BrandVariants = {
  10: "#020410",
  20: "#0a1330",
  30: "#0d1f4d",
  40: "#172554", // blue-950
  50: "#1e3a8a", // blue-900
  60: "#1e40af", // blue-800
  70: "#1d4ed8", // blue-700
  80: "#2563eb", // blue-600 — light-mode primary
  90: "#3b82f6", // blue-500 — dark-mode primary (Fluent picks step 100 by default,
  100: "#60a5fa", // blue-400   but step 90 → 100 gives us a familiar accent range)
  110: "#93c5fd", // blue-300
  120: "#bfdbfe", // blue-200
  130: "#dbeafe", // blue-100
  140: "#eff6ff", // blue-50
  150: "#f5faff",
  160: "#ffffff",
};
