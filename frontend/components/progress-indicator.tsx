// frontend/components/progress-indicator.tsx
import { Skeleton } from "@/components/ui/skeleton";
import type { ProgressStage } from "@/lib/types";

const STAGES: { key: ProgressStage; label: string }[] = [
  { key: "fetching",  label: "Fetching tweets\u2026" },
  { key: "parsing",   label: "Parsing tweets\u2026" },
  { key: "analyzing", label: "Running AI analysis\u2026" },
  { key: "done",      label: "Done" },
];

const ORDER: ProgressStage[] = ["fetching", "parsing", "analyzing", "done"];

interface ProgressIndicatorProps {
  stage: ProgressStage;
  message: string;
}

export function ProgressIndicator({ stage, message }: ProgressIndicatorProps) {
  const currentIdx = ORDER.indexOf(stage);
  return (
    <div aria-live="polite" className="space-y-3 py-8">
      {STAGES.map(({ key, label }, idx) => {
        const done = idx < currentIdx;
        const active = idx === currentIdx;
        return (
          <div key={key} className="flex items-center gap-3 text-sm">
            <span className="w-5 text-center">
              {done ? "✓" : active ? "⟳" : "○"}
            </span>
            <span
              className={
                done
                  ? "text-muted-foreground line-through"
                  : active
                  ? "font-medium"
                  : "text-muted-foreground"
              }
            >
              {active ? message : label}
            </span>
          </div>
        );
      })}
      <Skeleton className="mt-4 h-32 w-full" />
    </div>
  );
}
