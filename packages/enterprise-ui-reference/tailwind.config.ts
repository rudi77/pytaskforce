import type { Config } from "tailwindcss";
import preset from "@taskforce/ui-shell/tailwind.preset";

/**
 * Tailwind config for the enterprise UI plugin.
 *
 * The host (pytaskforce/ui) already builds its own CSS using the same
 * preset and adds this package's `dist/` to its `content` glob, so
 * the plugin does not strictly need its own build of Tailwind. This
 * config is provided for local development (running the plugin
 * standalone in Storybook, vitest, etc.) and to lock in the same
 * tokens the host uses.
 */
const config: Config = {
  presets: [preset as Config],
  content: ["./src/**/*.{ts,tsx}"],
};

export default config;
