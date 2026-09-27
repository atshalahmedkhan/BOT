export type Article = {
  id: number; title: string; description: string; url: string; source: string;
  category: string; topic: string; score: number; reason: string;
  published_at: string | null; seen_at: string; skipped: boolean;
};
export type Post = {
  id: number; article_id: number | null; text: string; style: string;
  status: string; failure_reason: string; confidence: number;
  created_at: string; published_at: string | null; scheduled_at: string | null;
  publisher_response: { post_id?: string; provider?: string } | null;
  feedback: string | null; feedback_reason: string | null;
};
export type Run = { id: number; status: string; detail: string; started_at: string; stories_fetched: number };
export type Automation = {
  paused: boolean; discover: boolean; generate: boolean; publish_without_approval: boolean;
  post_times: string[]; timezone: string; minimum_relevance: number; dry_run: boolean;
};
export type WorkspaceData = { articles: Article[]; posts: Post[]; runs: Run[]; automation: Automation };
export type Source = { name: string; url: string; category: string; priority: number; enabled: boolean };

export type Entry = { key: string; article?: Article; post?: Post; status: string; title: string; source: string; topic: string; style: string; score: number; date: string | null };
