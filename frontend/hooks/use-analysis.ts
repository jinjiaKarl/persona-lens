// frontend/hooks/use-analysis.ts
"use client";

import { useState, useCallback } from "react";
import type { AnalysisState, AnalysisResult, ProgressEvent } from "@/lib/types";

const API_BASE = "http://localhost:8000";

export function useAnalysis(sessionId: string, userId: string = "default") {
  const [state, setState] = useState<AnalysisState>({
    status: "idle",
    progress: null,
    result: null,
    error: null,
  });

  const analyze = useCallback(async (username: string, tweets: number) => {
    setState({ status: "loading", progress: null, result: null, error: null });

    try {
      const res = await fetch(
        `${API_BASE}/api/analyze/${encodeURIComponent(username)}?tweets=${tweets}&session_id=${encodeURIComponent(sessionId)}&user_id=${encodeURIComponent(userId)}`,
        { method: "POST" }
      );

      if (!res.ok || !res.body) {
        throw new Error(`Server error: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            if (currentEvent === "progress") {
              setState((s) => ({ ...s, progress: data as ProgressEvent }));
            } else if (currentEvent === "result") {
              setState({
                status: "success",
                progress: { stage: "done", message: "Done" },
                result: data as AnalysisResult,
                error: null,
              });
            } else if (currentEvent === "error") {
              setState({
                status: "error",
                progress: null,
                result: null,
                error: data,
              });
            }
            currentEvent = "";
          }
        }
      }
    } catch (err) {
      setState({
        status: "error",
        progress: null,
        result: null,
        error: {
          error: err instanceof Error ? err.message : String(err),
          fix: "Make sure the FastAPI server is running: uv run uvicorn persona_lens.api.server:app --port 8000",
        },
      });
    }
  }, [sessionId, userId]);

  return { state, analyze };
}
