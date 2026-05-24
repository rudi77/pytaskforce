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
 * by `<FluentProvider>` in `src/main.tsx` via `FluentThemeBridge`. The bridge
 * picks one of these based on the existing `ThemeProvider` (`useTheme()`)
 * so the dark-mode toggle is preserved during the shadcn → Fluent migration.
 */
export const lightTheme: Theme = createLightTheme(taskforceBrand);
export const darkTheme: Theme = createDarkTheme(taskforceBrand);
