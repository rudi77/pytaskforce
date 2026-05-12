# @taskforce/enterprise-ui (reference stub)

This package is a **no-op reference implementation** of the
`@taskforce/enterprise-ui` plugin that ships in the (private)
`taskforce-enterprise` repository. It exists so:

1. The framework UI's optional plugin dependency
   (`ui/package.json` → `optionalDependencies` → `@taskforce/enterprise-ui`)
   resolves locally — no cross-repo checkout, no GITHUB_TOKEN gymnastics,
   no leaking the commercial package into the public CI logs.
2. The framework's plugin loader test
   (`ui/src/plugins/loader.test.ts`) has a registerable plugin to import
   so the bootstrap-and-register codepath stays covered.

The real plugin replaces this stub in deployments that install
`taskforce-enterprise`. The dev launcher (`dev.ps1 -Install`) overwrites
`ui/node_modules/@taskforce/enterprise-ui/` with a build of
`taskforce-enterprise/web/`; the enterprise wheel does the same at
install time.

## What this stub contributes

Just enough to keep the contract honest: a single plugin object with
`id="enterprise"`, the `admin.tenants` capability, and two placeholder
nav items + routes whose components return `null`. The placeholders are
never rendered — anything trying to consume the real enterprise UI in a
deployment that didn't install the plugin gets the host's default
"not-found" path.

If you add a new capability or route to the real plugin and want CI to
cover it, mirror it here. The stub is intentionally tiny; keep it that
way.
