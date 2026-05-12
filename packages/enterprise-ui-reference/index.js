// No-op reference stub for `@taskforce/enterprise-ui`.
//
// This package exists so the framework UI's optional dependency
// (`ui/package.json` → `optionalDependencies` → `@taskforce/enterprise-ui`)
// resolves *within this repo* and the bundled `bootstrapPlugins()` loader
// has a registerable plugin to import. The real enterprise plugin ships
// from `taskforce-enterprise/web/` and overrides this stub in production
// deployments (the dev launcher and the enterprise install both write to
// `ui/node_modules/@taskforce/enterprise-ui/` directly).
//
// Capabilities + nav/routes mirror the contract the host's
// `loader.test.ts` checks (`admin.tenants` capability, non-empty nav and
// routes). The shapes are intentionally minimal — the stub is loaded by
// tests and by CI; it is never rendered.

const placeholder = () => null;

/** @type {import("@taskforce/ui-shell").UIPlugin} */
const enterprisePlugin = {
  id: "enterprise",
  displayName: "Enterprise (reference stub)",
  version: "0.0.0-reference",
  capabilities: [
    "admin.tenants",
    "admin.users",
    "admin.roles",
    "admin.audit",
    "admin.agents",
  ],
  navItems: [
    {
      to: "/admin/tenants",
      label: "Tenants",
      icon: placeholder,
      section: "admin",
    },
    {
      to: "/admin/users",
      label: "Users & Roles",
      icon: placeholder,
      section: "admin",
    },
  ],
  routes: [
    { path: "admin/tenants", element: placeholder },
    { path: "admin/users", element: placeholder },
  ],
};

export function register(registry) {
  registry.register(enterprisePlugin);
}

export default { register };
