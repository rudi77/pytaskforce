import * as React from "react";
import { TabList, Tab as FluentTab } from "@fluentui/react-components";
import { cn } from "@/lib/utils";

/**
 * shadcn-API-compatible Tabs wrapping FluentUI v9 TabList.
 *
 * Radix Tabs is uncontrolled-by-default (defaultValue) with multiple
 * TabsContent that filter by matching `value`. Fluent TabList only
 * provides the tab strip — the consumer renders the active body
 * themselves. This wrapper bridges the two by holding the active
 * value in a context and short-circuiting TabsContent for the
 * non-matching values.
 *
 * The single consumer in this repo (SettingsPage already migrated
 * to native Fluent; AgentProfileEditor still uses this) keeps the
 * defaultValue/onValueChange/value triple.
 */

interface TabsContextValue {
  value: string;
  setValue: (next: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  defaultValue?: string;
  value?: string;
  onValueChange?: (next: string) => void;
}

export function Tabs({
  defaultValue,
  value,
  onValueChange,
  className,
  children,
  ...rest
}: TabsProps) {
  const [internal, setInternal] = React.useState(defaultValue ?? "");
  const current = value ?? internal;
  const setCurrent = React.useCallback(
    (next: string) => {
      if (value === undefined) setInternal(next);
      onValueChange?.(next);
    },
    [value, onValueChange],
  );
  return (
    <TabsContext.Provider value={{ value: current, setValue: setCurrent }}>
      <div className={className} {...rest}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

interface TabsListProps extends React.HTMLAttributes<HTMLDivElement> {}

export const TabsList = React.forwardRef<HTMLDivElement, TabsListProps>(
  ({ className, children, ...rest }, ref) => {
    const ctx = React.useContext(TabsContext);
    if (!ctx) throw new Error("<TabsList> must be inside <Tabs>");
    return (
      <div ref={ref} className={className} {...rest}>
        <TabList
          selectedValue={ctx.value}
          onTabSelect={(_, data) => ctx.setValue(String(data.value))}
        >
          {children}
        </TabList>
      </div>
    );
  },
);
TabsList.displayName = "TabsList";

interface TabsTriggerProps extends React.HTMLAttributes<HTMLButtonElement> {
  value: string;
  disabled?: boolean;
}

export function TabsTrigger({ value, children, disabled, className }: TabsTriggerProps) {
  return (
    <FluentTab value={value} disabled={disabled} className={className}>
      {children}
    </FluentTab>
  );
}

interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
}

export function TabsContent({ value, className, children, ...rest }: TabsContentProps) {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error("<TabsContent> must be inside <Tabs>");
  if (ctx.value !== value) return null;
  return (
    <div className={cn("mt-4 focus-visible:outline-none", className)} {...rest}>
      {children}
    </div>
  );
}
