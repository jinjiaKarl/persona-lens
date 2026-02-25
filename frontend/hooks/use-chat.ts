// frontend/hooks/use-chat.ts
"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import type { ChatState, ChatMessage, AnalysisResult } from "@/lib/types";

const API_BASE = "http://localhost:8000";

function makeId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  const key = "persona-lens-session-id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

const WELCOME: ChatMessage = {
  id: "system-welcome",
  role: "system",
  content: "Hi! Ask me to analyze an X/Twitter user, or ask questions about any analyzed profile.",
  isStreaming: false,
  toolCalls: [],
};

interface UseChatOptions {
  onAnalysisResult?: (result: AnalysisResult) => void;
}

export function useChat({ onAnalysisResult }: UseChatOptions = {}) {
  const [state, setState] = useState<ChatState>({
    messages: [WELCOME],
    isStreaming: false,
  });
  const sessionIdRef = useRef<string>("default");

  useEffect(() => {
    sessionIdRef.current = getOrCreateSessionId();
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim()) return;

      const userMsg: ChatMessage = {
        id: makeId(),
        role: "user",
        content: text,
        isStreaming: false,
        toolCalls: [],
      };

      const agentMsgId = makeId();
      const agentMsg: ChatMessage = {
        id: agentMsgId,
        role: "agent",
        content: "",
        isStreaming: true,
        toolCalls: [],
      };

      setState((s) => ({
        messages: [...s.messages, userMsg, agentMsg],
        isStreaming: true,
      }));

      try {
        const res = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            session_id: sessionIdRef.current,
          }),
        });

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
              const rawData = line.slice(6);
              let data: Record<string, unknown>;
              try {
                data = JSON.parse(rawData);
              } catch {
                continue;
              }

              if (currentEvent === "token") {
                const delta = (data.delta as string) ?? "";
                setState((s) => ({
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === agentMsgId
                      ? { ...m, content: m.content + delta }
                      : m
                  ),
                }));
              } else if (currentEvent === "tool_call") {
                const toolCall = { tool: data.tool as string, status: "running" as const };
                setState((s) => ({
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === agentMsgId
                      ? { ...m, toolCalls: [...m.toolCalls, toolCall] }
                      : m
                  ),
                }));
              } else if (currentEvent === "analysis_result") {
                onAnalysisResult?.(data as unknown as AnalysisResult);
              } else if (currentEvent === "error") {
                setState((s) => ({
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === agentMsgId
                      ? { ...m, isStreaming: false, error: data as { error: string; fix: string } }
                      : m
                  ),
                  isStreaming: false,
                }));
              } else if (currentEvent === "done") {
                setState((s) => ({
                  messages: s.messages.map((m) =>
                    m.id === agentMsgId ? { ...m, isStreaming: false } : m
                  ),
                  isStreaming: false,
                }));
              }
              currentEvent = "";
            }
          }
        }
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err);
        setState((s) => ({
          messages: s.messages.map((m) =>
            m.id === agentMsgId
              ? {
                  ...m,
                  isStreaming: false,
                  error: {
                    error: errMsg,
                    fix: "Make sure the FastAPI server is running: uv run uvicorn persona_lens.api.server:app --port 8000",
                  },
                }
              : m
          ),
          isStreaming: false,
        }));
      }
    },
    [onAnalysisResult]
  );

  return { state, sendMessage };
}
