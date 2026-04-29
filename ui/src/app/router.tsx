import { createBrowserRouter, Navigate } from "react-router-dom";
import { lazy, Suspense } from "react";
import { AppShell } from "@/app/AppShell";

const Dashboard = lazy(() => import("@/pages/DashboardPage"));
const AgentsList = lazy(() => import("@/pages/AgentsListPage"));
const AgentEditor = lazy(() => import("@/pages/AgentEditorPage"));
const ChatPage = lazy(() => import("@/pages/ChatPage"));
const MonitoringPage = lazy(() => import("@/pages/MonitoringPage"));
const AcpPage = lazy(() => import("@/pages/AcpPage"));
const ToolsPage = lazy(() => import("@/pages/ToolsPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

function PageFallback() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      Loading…
    </div>
  );
}

function withSuspense(node: React.ReactNode) {
  return <Suspense fallback={<PageFallback />}>{node}</Suspense>;
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: withSuspense(<Dashboard />) },
      { path: "agents", element: withSuspense(<AgentsList />) },
      { path: "agents/new", element: withSuspense(<AgentEditor mode="create" />) },
      { path: "agents/:agentId", element: withSuspense(<AgentEditor mode="edit" />) },
      { path: "chat", element: withSuspense(<ChatPage />) },
      { path: "chat/:conversationId", element: withSuspense(<ChatPage />) },
      { path: "monitoring", element: withSuspense(<MonitoringPage />) },
      { path: "monitoring/runs/:sessionId", element: withSuspense(<MonitoringPage />) },
      { path: "acp", element: withSuspense(<AcpPage />) },
      { path: "tools", element: withSuspense(<ToolsPage />) },
      { path: "settings", element: withSuspense(<SettingsPage />) },
      { path: "*", element: withSuspense(<NotFoundPage />) },
    ],
  },
  { path: "/index.html", element: <Navigate to="/" replace /> },
]);
