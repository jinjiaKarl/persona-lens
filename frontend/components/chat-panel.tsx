// frontend/components/chat-panel.tsx
"use client";

import { useRef, useEffect, useState, FormEvent, KeyboardEvent } from "react";
import { ChatMessage } from "@/components/chat-message";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import type { AnalysisResult } from "@/lib/types";

interface ChatPanelProps {
  onAnalysisResult?: (result: AnalysisResult) => void;
}

export function ChatPanel({ onAnalysisResult }: ChatPanelProps) {
  const { state, sendMessage } = useChat({ onAnalysisResult });
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.messages]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || state.isStreaming) return;
    setInput("");
    sendMessage(text);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = input.trim();
      if (!text || state.isStreaming) return;
      setInput("");
      sendMessage(text);
    }
  }

  return (
    <div className="flex flex-col h-full border rounded-lg overflow-hidden">
      {/* Message list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 space-y-3 overscroll-contain"
        aria-live="polite"
        aria-label="Chat messages"
      >
        {state.messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
      </div>

      {/* Input bar */}
      <form
        onSubmit={handleSubmit}
        className="border-t p-2 flex gap-2 items-end"
      >
        <div className="flex-1">
          <label htmlFor="chat-input" className="sr-only">
            Message
          </label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a KOL, or type 'analyze @username'\u2026"
            autoComplete="off"
            spellCheck={false}
            disabled={state.isStreaming}
            rows={1}
            className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            style={{ touchAction: "manipulation", maxHeight: "120px" }}
          />
        </div>
        <Button
          type="submit"
          size="sm"
          disabled={!input.trim() || state.isStreaming}
          aria-label="Send message"
          style={{ touchAction: "manipulation" }}
        >
          {state.isStreaming ? "\u22EF" : "Send"}
        </Button>
      </form>
    </div>
  );
}
