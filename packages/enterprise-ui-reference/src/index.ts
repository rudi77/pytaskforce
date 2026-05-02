/**
 * Public entry of the `@taskforce/enterprise-ui` package.
 *
 * The host pytaskforce/ui calls `register(registry)` exactly once at
 * startup (see `ui/src/plugins/loader.ts`). Default-export is also
 * supported in case the host moves to a default-import convention
 * later.
 */
import type { PluginRegistry } from "@taskforce/ui-shell";

import { enterpriseUIPlugin } from "./plugin";

export { enterpriseUIPlugin };

export function register(registry: PluginRegistry): void {
  registry.register(enterpriseUIPlugin);
}

export default { register };
