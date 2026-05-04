import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { configureApiClient } from "@taskforce/ui-shell";

import { AppBootstrap } from "@/app/AppBootstrap";
import { buildRouter } from "@/app/router";
import { ThemeProvider } from "@/app/theme-provider";
import { Toaster } from "@/components/ui/toast";
import { getApiBaseUrl, getApiToken, useSettings } from "@/lib/settings";
import { bootstrapPlugins } from "@/plugins/loader";
import "@/app/globals.css";

// Wire the shared HTTP client to the host's settings store BEFORE any
// plugin module is imported — plugins read the singleton lazily on
// first request, but registering early avoids a race in the rare case
// a plugin fires a request from `register()`.
configureApiClient({
  getBaseUrl: () => getApiBaseUrl(),
  getToken: () => getApiToken() || null,
  onUnauthorized: () => {
    console.warn("[auth] 401 received, clearing token + redirecting to /login");
    useSettings.getState().setApiToken("");
    if (window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
  },
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

async function main() {
  // Register optional UI plugins (no-op when none are installed) so
  // their routes are present in the router built below.
  await bootstrapPlugins();
  const router = buildRouter();

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <AppBootstrap>
            <RouterProvider router={router} />
          </AppBootstrap>
          <Toaster />
        </QueryClientProvider>
      </ThemeProvider>
    </React.StrictMode>,
  );
}

void main();
