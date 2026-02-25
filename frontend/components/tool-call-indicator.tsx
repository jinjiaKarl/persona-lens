// frontend/components/tool-call-indicator.tsx
import type { ToolCallInfo } from "@/lib/types";

const TOOL_LABELS: Record<string, string> = {
  fetch_user: "Fetching tweets\u2026",
  analyze_user: "Running AI analysis\u2026",
};

interface ToolCallIndicatorProps {
  toolCalls: ToolCallInfo[];
}

export function ToolCallIndicator({ toolCalls }: ToolCallIndicatorProps) {
  if (toolCalls.length === 0) return null;
  return (
    <div className="space-y-1 mb-2">
      {toolCalls.map((tc, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
          <span aria-hidden="true">→</span>
          <span>{TOOL_LABELS[tc.tool] ?? `${tc.tool}\u2026`}</span>
        </div>
      ))}
    </div>
  );
}
