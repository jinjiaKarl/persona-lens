// frontend/components/tweet-list.tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatDate, formatExact } from "@/lib/format";
import type { Tweet } from "@/lib/types";

type SortKey = "time" | "likes" | "retweets";

interface TweetListProps {
  tweets: Tweet[];
  username: string;
}

function exportJSON(tweets: Tweet[], username: string) {
  const blob = new Blob([JSON.stringify(tweets, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${username}-tweets.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function exportCSV(tweets: Tweet[], username: string) {
  const header = "id,text,timestamp_ms,likes,retweets,replies,views";
  const rows = tweets.map((t) =>
    [t.id, JSON.stringify(t.text), t.timestamp_ms, t.likes, t.retweets, t.replies, t.views].join(",")
  );
  const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${username}-tweets.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function TweetList({ tweets, username }: TweetListProps) {
  const [sort, setSort] = useState<SortKey>("time");
  const [expanded, setExpanded] = useState(false);

  const sorted = [...tweets].sort((a, b) => {
    if (sort === "likes") return b.likes - a.likes;
    if (sort === "retweets") return b.retweets - a.retweets;
    return b.timestamp_ms - a.timestamp_ms;
  });

  const visible = expanded ? sorted : sorted.slice(0, 10);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>All Tweets ({tweets.length})</CardTitle>
          <div className="flex items-center gap-2">
            <label htmlFor="tweet-sort" className="sr-only">Sort tweets by</label>
            <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
              <SelectTrigger
                id="tweet-sort"
                className="w-36 h-8 text-xs"
                style={{ touchAction: "manipulation" }}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="time">Sort: Time</SelectItem>
                <SelectItem value="likes">Sort: Likes</SelectItem>
                <SelectItem value="retweets">Sort: Retweets</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              aria-label="Export tweets as JSON"
              style={{ touchAction: "manipulation" }}
              onClick={() => exportJSON(tweets, username)}
            >
              Export JSON
            </Button>
            <Button
              variant="outline"
              size="sm"
              aria-label="Export tweets as CSV"
              style={{ touchAction: "manipulation" }}
              onClick={() => exportCSV(tweets, username)}
            >
              Export CSV
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {visible.map((t) => (
          <div key={t.id} className="border-b pb-3 last:border-0 last:pb-0">
            <p className="text-sm line-clamp-3 min-w-0 break-words">{t.text}</p>
            <div
              className="flex gap-4 mt-1 text-xs text-muted-foreground"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {t.timestamp_ms > 0 && <span>{formatDate(t.timestamp_ms)}</span>}
              <span>{formatExact(t.likes)} likes</span>
              <span>{formatExact(t.retweets)} RTs</span>
              <span>{formatExact(t.replies)} replies</span>
            </div>
          </div>
        ))}
        {tweets.length > 10 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            style={{ touchAction: "manipulation" }}
            onClick={() => setExpanded((e) => !e)}
          >
            {expanded ? "Show less" : `Show all ${tweets.length} tweets`}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
