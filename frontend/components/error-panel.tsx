// frontend/components/error-panel.tsx
import { Button } from "@/components/ui/button";

interface ErrorPanelProps {
  error: string;
  fix: string;
  onRetry: () => void;
}

export function ErrorPanel({ error, fix, onRetry }: ErrorPanelProps) {
  return (
    <div
      role="alert"
      aria-live="polite"
      className="rounded-lg border border-destructive/50 bg-destructive/10 p-6"
    >
      <p className="font-medium text-destructive">Analysis failed</p>
      <p className="mt-1 text-sm text-muted-foreground">{error}</p>
      {fix && (
        <p className="mt-2 text-sm font-mono bg-muted rounded px-2 py-1 inline-block">
          {fix}
        </p>
      )}
      <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
