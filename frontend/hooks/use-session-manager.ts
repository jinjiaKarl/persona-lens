// frontend/hooks/use-session-manager.ts
"use client";

import { useState, useCallback, useEffect } from "react";

export interface Session {
  id: string;
  title: string;
  createdAt: number;
}

interface SessionManagerState {
  sessions: Session[];
  activeSessionId: string;
}

const STORAGE_KEY = "persona-lens-sessions";

function makeSession(index: number): Session {
  return {
    id: crypto.randomUUID(),
    title: `Chat ${index}`,
    createdAt: Date.now(),
  };
}

function loadState(): SessionManagerState {
  if (typeof window === "undefined") {
    const s = makeSession(1);
    return { sessions: [s], activeSessionId: s.id };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as SessionManagerState;
      if (parsed.sessions.length > 0) return parsed;
    }
  } catch { /* ignore */ }
  const s = makeSession(1);
  return { sessions: [s], activeSessionId: s.id };
}

function saveState(state: SessionManagerState) {
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }
}

export function useSessionManager() {
  const [state, setState] = useState<SessionManagerState>(loadState);

  // Persist on every change
  useEffect(() => {
    saveState(state);
  }, [state]);

  const createSession = useCallback(() => {
    setState((prev) => {
      const newSession = makeSession(prev.sessions.length + 1);
      return {
        sessions: [...prev.sessions, newSession],
        activeSessionId: newSession.id,
      };
    });
  }, []);

  const switchSession = useCallback((id: string) => {
    setState((prev) => ({ ...prev, activeSessionId: id }));
  }, []);

  const deleteSession = useCallback((id: string) => {
    setState((prev) => {
      const remaining = prev.sessions.filter((s) => s.id !== id);
      if (remaining.length === 0) {
        const fresh = makeSession(1);
        return { sessions: [fresh], activeSessionId: fresh.id };
      }
      const activeId =
        prev.activeSessionId === id ? remaining[remaining.length - 1].id : prev.activeSessionId;
      return { sessions: remaining, activeSessionId: activeId };
    });
  }, []);

  const renameSession = useCallback((id: string, title: string) => {
    setState((prev) => ({
      ...prev,
      sessions: prev.sessions.map((s) =>
        s.id === id ? { ...s, title: title.slice(0, 30) } : s
      ),
    }));
  }, []);

  const activeSession = state.sessions.find((s) => s.id === state.activeSessionId)!;

  return {
    sessions: state.sessions,
    activeSession,
    activeSessionId: state.activeSessionId,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
  };
}
