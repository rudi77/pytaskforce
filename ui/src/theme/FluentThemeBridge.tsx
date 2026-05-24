import { FluentProvider } from "@fluentui/react-components";
import type { ReactNode } from "react";

import { useTheme } from "@/app/theme-provider";

import { darkTheme, lightTheme } from "./themes";

interface Props {
  children: ReactNode;
}

/**
 * Wires the existing `ThemeProvider` (`useTheme()`) to `<FluentProvider>` so
 * the dark-mode toggle drives FluentUI v9 components during the shadcn →
 * Fluent migration.
 *
 * Lives between `ThemeProvider` (owns the `dark` class on `<html>` for
 * shadcn-era Tailwind utilities) and the rest of the tree so both systems
 * see the same theme decision.
 */
export function FluentThemeBridge({ children }: Props) {
  const { theme } = useTheme();
  return (
    <FluentProvider theme={theme === "dark" ? darkTheme : lightTheme}>
      {children}
    </FluentProvider>
  );
}
