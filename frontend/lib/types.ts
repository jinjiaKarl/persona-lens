// frontend/lib/types.ts

export interface UserInfo {
  username: string;
  display_name: string;
  bio: string;
  joined: string;
  tweets_count: number;
  followers: number;
  following: number;
}

export interface Tweet {
  id: string;
  text: string;
  timestamp_ms: number;
  likes: number;
  retweets: number;
  replies: number;
  views: number;
  author: string | null;
  author_name: string | null;
  media: string[];
  has_media: boolean;
  time_ago: string | null;
}

export interface ProductItem {
  product: string;
  category: string;
}

export interface TopPost {
  text: string;
  likes: number;
  retweets: number;
}

export interface AnalysisResult {
  user_info: UserInfo;
  tweets: Tweet[];
  patterns: {
    peak_days: Record<string, number>;
    peak_hours: Record<string, number>;
  };
  analysis: {
    products: ProductItem[];
    writing_style: string;
    engagement: {
      top_posts: TopPost[];
      insights: string;
    };
  };
}

// ── Chat types ──────────────────────────────────────────────────────────────

export interface ToolCallInfo {
  tool: string;
  status: "running" | "done";
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent" | "system";
  content: string;       // accumulated text (built up from token deltas)
  isStreaming: boolean;  // true while receiving tokens
  toolCalls: ToolCallInfo[];
  error?: { error: string; fix: string };
}

export interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
}

export type ProgressStage = "fetching" | "parsing" | "analyzing" | "done";

export interface ProgressEvent {
  stage: ProgressStage;
  message: string;
}

export interface AnalysisState {
  status: "idle" | "loading" | "success" | "error";
  progress: ProgressEvent | null;
  result: AnalysisResult | null;
  error: { error: string; fix: string } | null;
}
