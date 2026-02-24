// frontend/components/search-bar.tsx
"use client";

import { useState, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

interface SearchBarProps {
  onAnalyze: (username: string, tweets: number) => void;
  isLoading: boolean;
  initialUsername?: string;
  initialTweets?: number;
}

export function SearchBar({
  onAnalyze,
  isLoading,
  initialUsername = "",
  initialTweets = 30,
}: SearchBarProps) {
  const [username, setUsername] = useState(initialUsername);
  const [tweets, setTweets] = useState(String(initialTweets));

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = username.replace(/^@/, "").trim();
    if (!trimmed) return;
    onAnalyze(trimmed, Number(tweets));
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <div className="flex-1">
        <Label htmlFor="username-input" className="sr-only">
          X/Twitter username
        </Label>
        <Input
          id="username-input"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="e.g. karpathy\u2026"
          autoComplete="off"
          spellCheck={false}
          disabled={isLoading}
          className="h-9"
          style={{ touchAction: "manipulation" }}
        />
      </div>
      <div>
        <Label htmlFor="tweet-count" className="sr-only">Number of tweets</Label>
        <Select value={tweets} onValueChange={setTweets} disabled={isLoading}>
          <SelectTrigger
            id="tweet-count"
            className="w-24 h-9"
            style={{ touchAction: "manipulation" }}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[20, 30, 50, 100].map((n) => (
              <SelectItem key={n} value={String(n)}>{n} tweets</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button
        type="submit"
        disabled={isLoading || !username.trim()}
        className="h-9"
        style={{ touchAction: "manipulation" }}
      >
        {isLoading ? "Analyzing\u2026" : "Analyze"}
      </Button>
    </form>
  );
}
