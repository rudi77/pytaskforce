/**
 * Public surface of `@taskforce/ui-shell`.
 *
 * The package exports:
 *  - shadcn-derived UI primitives shared between the host UI and any
 *    UI plugin so they look and behave identically.
 *  - the `apiFetch` / `sseStream` HTTP client driven by an injectable
 *    auth + base-url provider (see {@link configureApiClient}).
 *  - the plugin contract types (`UIPlugin`, `PluginRegistry`, ...).
 *  - the Tailwind preset (re-exported via the `./tailwind.preset`
 *    sub-path, not from this barrel).
 */

// Utilities
export { cn } from "./lib/utils";

// API client
export {
  apiFetch,
  sseStream,
  ApiError,
  configureApiClient,
  resetApiClient,
  type ApiClientConfig,
} from "./api/client";

// Plugin contract
export type {
  UIPlugin,
  PluginNavItem,
  PluginRoute,
  PluginRegistry,
  PluginContext,
} from "./plugins/types";

// shadcn-derived primitives
export { Button, buttonVariants, type ButtonProps } from "./components/ui/button";
export {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./components/ui/card";
export { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
} from "./components/ui/dialog";
export { Input } from "./components/ui/input";
export { Label } from "./components/ui/label";
export { Badge, type BadgeProps } from "./components/ui/badge";
export { Skeleton } from "./components/ui/skeleton";
export { Textarea } from "./components/ui/textarea";
export { Toaster, toast } from "./components/ui/toast";
