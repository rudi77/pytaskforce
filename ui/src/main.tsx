import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AppBootstrap } from "@/app/AppBootstrap";
import { buildRouter } from "@/app/router";
import { ThemeProvider } from "@/app/theme-provider";
import { Toaster } from "@/components/ui/toast";
import { bootstrapPlugins } from "@/plugins/loader";
import "@/app/globals.css";

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
