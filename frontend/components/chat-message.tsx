// frontend/components/chat-message.tsx
import { ToolCallIndicator } from "@/components/tool-call-indicator";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const { role, content, isStreaming, toolCalls, error } = message;

  if (role === "system") {
    return (
      <div className="text-xs text-muted-foreground italic px-1 py-2">
        {content}
      </div>
    );
  }

  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        }`}
      >
        {!isUser && <ToolCallIndicator toolCalls={toolCalls} />}
        {content && (
          <p className="whitespace-pre-wrap break-words min-w-0">
            {content}
            {isStreaming && (
              <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-current animate-pulse align-middle" aria-hidden="true" />
            )}
          </p>
        )}
        {!content && isStreaming && !toolCalls.length && (
          <p className="text-muted-foreground/60">Thinking…</p>
        )}
        {error && (
          <div className="mt-2">
            <p className="text-destructive text-xs font-medium">{error.error}</p>
            {error.fix && (
              <p className="text-xs font-mono bg-background/50 rounded px-1 py-0.5 mt-1">
                {error.fix}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
