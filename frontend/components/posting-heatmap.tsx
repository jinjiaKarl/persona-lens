// frontend/components/posting-heatmap.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const HOURS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"];

interface PostingHeatmapProps {
  peakDays: Record<string, number>;
  peakHours: Record<string, number>;
}

function Bar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div
      className="flex items-center gap-2 text-xs"
      style={{ fontVariantNumeric: "tabular-nums" }}
    >
      <div
        className="h-3 rounded-sm bg-primary transition-[width,opacity] duration-300 motion-reduce:transition-none"
        style={{ width: `${pct}%`, minWidth: pct > 0 ? "2px" : "0" }}
        aria-hidden="true"
      />
      <span className="text-muted-foreground">{value}</span>
    </div>
  );
}

export function PostingHeatmap({ peakDays, peakHours }: PostingHeatmapProps) {
  const maxDay = Math.max(...Object.values(peakDays), 1);
  const maxHour = Math.max(...Object.values(peakHours), 1);
  const topDay = Object.entries(peakDays).sort((a, b) => b[1] - a[1])[0]?.[0];
  const topHour = Object.entries(peakHours).sort((a, b) => b[1] - a[1])[0]?.[0];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Posting Patterns</CardTitle>
        {topDay && (
          <p className="text-xs text-muted-foreground">
            Peak: {topDay}, {topHour} UTC
          </p>
        )}
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-6">
        <div>
          <h3 className="text-xs font-medium mb-2">By Day</h3>
          <div className="space-y-1">
            {DAYS.map((d) => (
              <div
                key={d}
                className="grid items-center gap-2"
                style={{ gridTemplateColumns: "6rem 1fr" }}
              >
                <span className="text-xs text-muted-foreground truncate">{d}</span>
                <Bar value={peakDays[d] ?? 0} max={maxDay} />
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-xs font-medium mb-2">By Hour (UTC)</h3>
          <div className="space-y-1">
            {HOURS.map((h) => (
              <div
                key={h}
                className="grid items-center gap-2"
                style={{ gridTemplateColumns: "4rem 1fr" }}
              >
                <span className="text-xs text-muted-foreground">{h}</span>
                <Bar value={peakHours[h] ?? 0} max={maxHour} />
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
