import type { Article, Entry, Post } from "./types";

export function entries(articles: Article[], posts: Post[]): Entry[] {
  const latest = new Map<number, Post>();
  for (const post of posts) if (post.article_id && !latest.has(post.article_id)) latest.set(post.article_id, post);
  const articleEntries = articles.map((article) => {
    const post = latest.get(article.id);
    return {
      key: `article-${article.id}`, article, post,
      status: article.skipped ? "Skipped" : post ? labelStatus(post.status) : "Discovered",
      title: article.title, source: article.source, topic: article.topic || article.category,
      style: post?.style || "", score: Math.min(100, Math.round(article.score)),
      date: post?.scheduled_at || post?.published_at || null,
    };
  });
  const customEntries = posts.filter((post) => !post.article_id).map((post) => ({
    key: `post-${post.id}`, post, status: labelStatus(post.status), title: post.text.split("\n")[0],
    source: "Manual idea", topic: "Custom", style: post.style, score: 0,
    date: post.scheduled_at || post.published_at,
  }));
  return [...articleEntries, ...customEntries];
}

export function labelStatus(status: string) {
  return ({ generated: "Ready", queued: "Scheduled", published: "Published", failed: "Failed", archived: "Archived", scheduled: "Scheduled" } as Record<string, string>)[status] || status;
}

export function dateLabel(value: string | null, zone = "America/New_York") {
  if (!value) return "—";
  const date = new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: zone }).format(date);
}

export function postLength(value: string) {
  return Array.from(value.replace(/https?:\/\/\S+/g, "x".repeat(23))).length;
}

export function instant(value: string) {
  return new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function relativeDate(value: string | null) {
  if (!value) return "Date unknown";
  const diff = Date.now() - new Date(value.endsWith("Z") ? value : `${value}Z`).getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)} min ago`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} hr ago`;
  return `${Math.round(minutes / 1440)} days ago`;
}

export function voiceLabel(value: string) {
  return ({ builder_perspective: "Builder", explanation: "Explanation", reaction: "Reaction", question: "Question", straightforward: "Straightforward" } as Record<string, string>)[value] || value || "—";
}

export function topicLabel(value: string) {
  const v = value.toLowerCase();
  if (v.includes("artificial") || v === "llm" || v === "model") return "AI";
  if (v.includes("agent")) return "Agents";
  if (v.includes("developer") || v.includes("software") || v === "coding") return "Dev Tools";
  if (v.includes("cyber") || v === "security") return "Security";
  return value.replace(/\b\w/g, (char) => char.toUpperCase());
}
