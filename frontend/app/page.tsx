// frontend/app/page.tsx
"use client";

import { useEffect, useCallback, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { SearchBar } from "@/components/search-bar";
import { ProgressIndicator } from "@/components/progress-indicator";
import { ProfileCard } from "@/components/profile-card";
import { ProductTags } from "@/components/product-tags";
import { WritingStyle } from "@/components/writing-style";
import { PostingHeatmap } from "@/components/posting-heatmap";
import { TopPosts } from "@/components/top-posts";
import { TweetList } from "@/components/tweet-list";
import { EmptyState } from "@/components/empty-state";
import { ErrorPanel } from "@/components/error-panel";
import { ChatPanel } from "@/components/chat-panel";
import { useAnalysis } from "@/hooks/use-analysis";
import { useSessionManager } from "@/hooks/use-session-manager";
import type { AnalysisResult } from "@/lib/types";

type MobileTab = "results" | "chat";

function AnalysisPage() {
  const router = useRouter();
  const params = useSearchParams();
  const {
    sessions,
    activeSessionId,
    isLoading: sessionsLoading,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
  } = useSessionManager();

  const { state, analyze } = useAnalysis(activeSessionId);

  // Per-session: { [sessionId]: { [username]: AnalysisResult } } — fetched from backend
  const [profilesBySession, setProfilesBySession] = useState<Record<string, Record<string, AnalysisResult>>>({});
  // Per-session: { [sessionId]: selectedUsername | null }
  const [selectedBySession, setSelectedBySession] = useState<Record<string, string | null>>({});

  // Fetch stored profiles from backend whenever the active session changes
  useEffect(() => {
    async function fetchProfiles() {
      try {
        const res = await fetch(`http://localhost:8000/api/sessions/${activeSessionId}/profiles`);
        if (!res.ok) return;
        const data: Record<string, AnalysisResult> = await res.json();
        if (Object.keys(data).length > 0) {
          setProfilesBySession(prev => ({ ...prev, [activeSessionId]: data }));
          // Auto-select the last analyzed username if none selected yet
          setSelectedBySession(prev => {
            if (prev[activeSessionId]) return prev;
            const last = Object.keys(data).at(-1) ?? null;
            return { ...prev, [activeSessionId]: last };
          });
        }
      } catch { /* backend not running */ }
    }
    fetchProfiles();
  }, [activeSessionId]);
  const [mobileTab, setMobileTab] = useState<MobileTab>("results");

  const initialUser = params.get("user") ?? "";
  const initialTweets = Number(params.get("tweets") ?? 30);

  useEffect(() => {
    if (initialUser) {
      analyze(initialUser, initialTweets);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAnalyze = useCallback(
    (username: string, tweets: number) => {
      router.push(`/?user=${encodeURIComponent(username)}&tweets=${tweets}`);
      analyze(username, tweets);
    },
    [router, analyze]
  );

  const analyzedProfiles = profilesBySession[activeSessionId] ?? {};
  const selectedUsername = selectedBySession[activeSessionId] ?? null;
  const displayResult = selectedUsername ? analyzedProfiles[selectedUsername] : null;

  const { status, progress, result, error } = state;

  useEffect(() => {
    if (result) {
      const username = result.user_info.username;
      setProfilesBySession(prev => ({
        ...prev,
        [activeSessionId]: { ...(prev[activeSessionId] ?? {}), [username]: result },
      }));
      setSelectedBySession(prev => ({ ...prev, [activeSessionId]: username }));
    }
  }, [result, activeSessionId]);

  // When chat triggers an analysis, add to map and switch to results tab on mobile
  const handleChatAnalysis = useCallback((chatResult: AnalysisResult) => {
    const username = chatResult.user_info.username;
    setProfilesBySession(prev => {
      const current = prev[activeSessionId] ?? {};
      // Auto-rename session to first analyzed username
      if (Object.keys(current).length === 0) {
        renameSession(activeSessionId, `@${username}`);
      }
      return { ...prev, [activeSessionId]: { ...current, [username]: chatResult } };
    });
    setSelectedBySession(prev => ({ ...prev, [activeSessionId]: username }));
    setMobileTab("results");
  }, [activeSessionId, renameSession]);

  // ── Analysis panel content ───────────────────────────────────────────────
  const analysisContent = (
    <div className="flex flex-col h-full overflow-y-auto space-y-4 pr-1">
      <SearchBar
        onAnalyze={handleAnalyze}
        isLoading={status === "loading"}
        initialUsername={initialUser}
        initialTweets={initialTweets}
      />

      {Object.keys(analyzedProfiles).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.keys(analyzedProfiles).map(username => (
            <button
              key={username}
              onClick={() => setSelectedBySession(prev => ({ ...prev, [activeSessionId]: username }))}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                selectedUsername === username
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
              style={{ touchAction: "manipulation" }}
            >
              @{username}
            </button>
          ))}
        </div>
      )}

      {status === "idle" && Object.keys(analyzedProfiles).length === 0 && <EmptyState />}

      {status === "loading" && progress && (
        <ProgressIndicator stage={progress.stage} message={progress.message} />
      )}

      {status === "error" && error && (
        <ErrorPanel
          error={error.error}
          fix={error.fix}
          onRetry={() => {
            const u = params.get("user") ?? "";
            const t = Number(params.get("tweets") ?? 30);
            if (u) analyze(u, t);
          }}
        />
      )}

      {displayResult && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <ProfileCard
              userInfo={displayResult.user_info}
              tweetsParsed={displayResult.tweets.length}
            />
            <ProductTags products={displayResult.analysis.products} />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <WritingStyle text={displayResult.analysis.writing_style} />
            <PostingHeatmap
              peakDays={displayResult.patterns.peak_days}
              peakHours={displayResult.patterns.peak_hours}
            />
          </div>

          <TopPosts
            insights={displayResult.analysis.engagement.insights}
            topPosts={displayResult.analysis.engagement.top_posts}
          />

          <TweetList
            tweets={displayResult.tweets}
            username={displayResult.user_info.username}
          />
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-screen">
      {/* Skip link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>

      <header className="px-4 py-3 border-b shrink-0">
        <h1 className="text-lg font-bold tracking-tight">Persona Lens</h1>
      </header>

      {sessionsLoading ? (
        <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
          Loading…
        </div>
      ) : (
        <>
          {/* ── Desktop: side-by-side ── */}
          <main
            id="main-content"
            className="hidden md:flex flex-1 overflow-hidden gap-0"
          >
            {/* Left: analysis panel */}
            <div className="w-3/5 overflow-y-auto p-4 border-r">
              {analysisContent}
            </div>

            {/* Right: chat panel */}
            <div className="w-2/5 p-3 flex flex-col">
              <ChatPanel
                key={activeSessionId}
                sessionId={activeSessionId}
                sessions={sessions}
                onNewSession={createSession}
                onSwitchSession={switchSession}
                onDeleteSession={deleteSession}
                onAnalysisResult={handleChatAnalysis}
              />
            </div>
          </main>

          {/* ── Mobile: tab switching ── */}
          <div className="md:hidden flex flex-col flex-1 overflow-hidden">
            {/* Tab bar */}
            <div
              role="tablist"
              aria-label="View"
              className="flex border-b shrink-0"
            >
              <button
                role="tab"
                aria-selected={mobileTab === "results"}
                aria-controls="panel-results"
                onClick={() => setMobileTab("results")}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  mobileTab === "results"
                    ? "border-b-2 border-primary text-primary"
                    : "text-muted-foreground"
                }`}
                style={{ touchAction: "manipulation" }}
              >
                Results
              </button>
              <button
                role="tab"
                aria-selected={mobileTab === "chat"}
                aria-controls="panel-chat"
                onClick={() => setMobileTab("chat")}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  mobileTab === "chat"
                    ? "border-b-2 border-primary text-primary"
                    : "text-muted-foreground"
                }`}
                style={{ touchAction: "manipulation" }}
              >
                Chat
              </button>
            </div>

            {/* Tab panels */}
            <div
              id="panel-results"
              role="tabpanel"
              hidden={mobileTab !== "results"}
              className="flex-1 overflow-y-auto p-4"
            >
              {analysisContent}
            </div>
            <div
              id="panel-chat"
              role="tabpanel"
              hidden={mobileTab !== "chat"}
              className="flex-1 overflow-hidden p-3 flex flex-col"
            >
              <ChatPanel
                key={activeSessionId}
                sessionId={activeSessionId}
                sessions={sessions}
                onNewSession={createSession}
                onSwitchSession={switchSession}
                onDeleteSession={deleteSession}
                onAnalysisResult={handleChatAnalysis}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function Home() {
  return (
    <Suspense fallback={<div className="h-screen" />}>
      <AnalysisPage />
    </Suspense>
  );
}
