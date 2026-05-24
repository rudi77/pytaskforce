import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <h2 className="text-2xl font-semibold tracking-tight">Page not found</h2>
      <p className="text-sm text-muted-foreground">
        The route you tried to reach does not exist.
      </p>
      <Button onClick={() => navigate("/")}>Back to dashboard</Button>
    </div>
  );
}
