// frontend/hooks/use-session-manager.ts
"use client";

import { useState, useCallback, useEffect } from "react";

export interface Session {
  session_id: string;
  title: string;
  created_at: number;
}

const API_BASE = "http://localhost:8000";
const ACTIVE_KEY = "persona-lens-active-session";
const DEFAULT_USER = "default";

function loadActiveId(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(ACTIVE_KEY) ?? "";
}

function saveActiveId(id: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(ACTIVE_KEY, id);
  }
}

export function useSessionManager(userId: string = DEFAULT_USER) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  // Fetch sessions from backend on mount
  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions`);
        if (!res.ok) throw new Error("Failed to fetch sessions");
        const data: Session[] = await res.json();

        if (data.length === 0) {
          // No sessions yet — create an initial one
          const id = crypto.randomUUID();
          let created: Session;
          try {
            created = await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ session_id: id, title: "Chat 1" }),
            }).then((r) => r.json()) as Session;
          } catch {
            created = { session_id: id, title: "Chat 1", created_at: Date.now() };
          }
          setSessions([created]);
          setActiveSessionId(id);
          saveActiveId(id);
        } else {
          setSessions(data);
          const saved = loadActiveId();
          const validId = data.find((s) => s.session_id === saved)?.session_id ?? data[data.length - 1].session_id;
          setActiveSessionId(validId);
          saveActiveId(validId);
        }
      } catch {
        // Backend not running — fall back to a synthetic local session
        const id = loadActiveId() || crypto.randomUUID();
        setSessions([{ session_id: id, title: "Chat 1", created_at: Date.now() }]);
        setActiveSessionId(id);
        saveActiveId(id);
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [userId]);

  const createSession = useCallback(async () => {
    const id = crypto.randomUUID();
    const title = `Chat ${sessions.length + 1}`;
    try {
      const created = await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: id, title }),
      }).then((r) => r.json()) as Session;
      setSessions((prev) => [...prev, created]);
      setActiveSessionId(id);
      saveActiveId(id);
    } catch {
      // Optimistic local fallback
      const s: Session = { session_id: id, title, created_at: Date.now() };
      setSessions((prev) => [...prev, s]);
      setActiveSessionId(id);
      saveActiveId(id);
    }
  }, [sessions, userId]);

  const switchSession = useCallback((id: string) => {
    setActiveSessionId(id);
    saveActiveId(id);
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    try {
      await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
    } catch {
      console.error("deleteSession: network error, proceeding optimistically");
    }

    setSessions((prev) => {
      const remaining = prev.filter((s) => s.session_id !== id);
      return remaining;
    });

    setActiveSessionId((cur) => {
      const remaining = sessions.filter((s) => s.session_id !== id);
      if (remaining.length === 0) {
        // Create a replacement session asynchronously
        const newId = crypto.randomUUID();
        fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: newId, title: "Chat 1" }),
        })
          .then((r) => r.json())
          .then((created: Session) => {
            setSessions([created]);
            setActiveSessionId(newId);
            saveActiveId(newId);
          })
          .catch(() => {
            const s: Session = { session_id: newId, title: "Chat 1", created_at: Date.now() };
            setSessions([s]);
            setActiveSessionId(newId);
            saveActiveId(newId);
          });
        return cur; // will be updated once the async create resolves
      }
      if (cur === id) {
        const next = remaining[remaining.length - 1].session_id;
        saveActiveId(next);
        return next;
      }
      return cur;
    });
  }, [sessions, userId]);

  const renameSession = useCallback(async (id: string, title: string) => {
    const trimmed = title.slice(0, 30);
    try {
      await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed }),
      });
    } catch {
      console.error("renameSession: network error, optimistic update applied");
    }
    setSessions((prev) =>
      prev.map((s) => (s.session_id === id ? { ...s, title: trimmed } : s))
    );
  }, [userId]);

  const activeSession = sessions.find((s) => s.session_id === activeSessionId) ?? sessions[0];

  return {
    sessions,
    activeSession,
    activeSessionId,
    isLoading,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
  };
}
