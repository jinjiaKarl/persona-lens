// frontend/app/page.tsx
"use client";

import { useEffect, useCallback, Suspense } from "react";
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
import { useAnalysis } from "@/hooks/use-analysis";

function AnalysisPage() {
  const router = useRouter();
  const params = useSearchParams();
  const { state, analyze } = useAnalysis();

  const initialUser = params.get("user") ?? "";
  const initialTweets = Number(params.get("tweets") ?? 30);

  // Auto-run if URL has a user param on first load
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

  const { status, progress, result, error } = state;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
      {/* Skip link for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>

      <header>
        <h1 className="text-xl font-bold tracking-tight text-balance mb-4">
          Persona Lens
        </h1>
        <SearchBar
          onAnalyze={handleAnalyze}
          isLoading={status === "loading"}
          initialUsername={initialUser}
          initialTweets={initialTweets}
        />
      </header>

      <main id="main-content">
        {status === "idle" && <EmptyState />}

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

        {status === "success" && result && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <ProfileCard
                userInfo={result.user_info}
                tweetsParsed={result.tweets.length}
              />
              <ProductTags products={result.analysis.products} />
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <WritingStyle text={result.analysis.writing_style} />
              <PostingHeatmap
                peakDays={result.patterns.peak_days}
                peakHours={result.patterns.peak_hours}
              />
            </div>

            <TopPosts
              insights={result.analysis.engagement.insights}
              topPosts={result.analysis.engagement.top_posts}
            />

            <TweetList
              tweets={result.tweets}
              username={result.user_info.username}
            />
          </div>
        )}
      </main>
    </div>
  );
}

export default function Home() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-8" />}>
      <AnalysisPage />
    </Suspense>
  );
}
