import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useSettings } from "@/lib/settings";

interface RequireAuthProps {
  children: ReactNode;
}

export function RequireAuth({ children }: RequireAuthProps) {
  const apiToken = useSettings((s) => s.apiToken);
  const location = useLocation();

  if (!apiToken) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
