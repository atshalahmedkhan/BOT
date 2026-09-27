"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Archive, ArrowUpDown, CalendarDays, Check, CheckCircle2, ChevronDown,
  ChevronLeft, ChevronRight, CircleDot, Clock3, ExternalLink, FilePenLine, Filter,
  LayoutGrid, MoreHorizontal, Plus, Search, Settings2,
  SquarePen, Star, WandSparkles, X, Zap, Loader2, Pause, Play, RotateCw, Save,
} from "lucide-react";
import { api, send } from "@/lib/api";
import { dateLabel, entries, instant, postLength, relativeDate, topicLabel, voiceLabel } from "@/lib/format";
import type { Article, Automation, Entry, Post, WorkspaceData } from "@/lib/types";

type View = "All content" | "Discover" | "Drafts" | "Calendar" | "By status" | "Published" | "Archive";
type SortKey = "score" | "newest" | "oldest" | "title" | "source";
const views: { name: View; icon: typeof Star }[] = [
  { name: "All content", icon: Star }, { name: "Discover", icon: CircleDot },
  { name: "Drafts", icon: SquarePen }, { name: "Calendar", icon: CalendarDays },
  { name: "By status", icon: LayoutGrid }, { name: "Published", icon: CheckCircle2 },
  { name: "Archive", icon: Archive },
];
const styles = ["builder_perspective", "reaction", "explanation", "question", "straightforward"];
const statusOrder = ["Ready", "Scheduled", "Discovered", "Published", "Failed", "Skipped", "Archived"];

function StatusTag({ value }: { value: string }) {
  return <span className={`status-tag status-${value.toLowerCase().replace(/\s/g, "-")}`}><span className="status-dot" />{value}</span>;
}
function TopicTag({ value }: { value: string }) {
  const label = topicLabel(value);
  const tone = /AI|Agents|Research/.test(label) ? "lavender" : /Dev|Software|Security/.test(label) ? "blue" : /Startup|Business/.test(label) ? "rose" : "green";
  return <span className={`database-tag tag-${tone}`}>{label}</span>;
}
function VoiceTag({ value }: { value: string }) { return value ? <span className="database-tag tag-neutral">{voiceLabel(value)}</span> : <span className="muted-dash">—</span>; }

function SkeletonRows() {
  return <div aria-label="Loading content" className="skeleton-wrap">{Array.from({ length: 11 }).map((_, index) => <div className="skeleton-row" key={index}><i /><i /><i /><i /><i /><i /></div>)}</div>;
}

export default function Workspace() {
  const router = useRouter();
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [view, setView] = useState<View>("All content");
  const [selected, setSelected] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("score");
  const [filter, setFilter] = useState<string>("All statuses");
  const [menu, setMenu] = useState<"filter" | "sort" | "automation" | "more" | "new" | null>(null);
  const [palette, setPalette] = useState(false);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [ideaOpen, setIdeaOpen] = useState(false);
  const [idea, setIdea] = useState("");
  const [month, setMonth] = useState(() => new Date());

  const refresh = useCallback(async () => {
    const result = await api<WorkspaceData>("/workspace");
    setData(result); setLoading(false);
  }, []);
  useEffect(() => { void Promise.resolve().then(refresh).catch((error) => { setNotice(`Could not load workspace: ${error.message}`); setLoading(false); }); }, [refresh]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setPalette(true); }
      if (event.key === "Escape") { setPalette(false); setSelected(null); setMenu(null); setIdeaOpen(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const all = useMemo(() => data ? entries(data.articles, data.posts) : [], [data]);
  const filtered = useMemo(() => {
    let list = all;
    if (view === "Discover") list = list.filter((entry) => entry.status === "Discovered");
    if (view === "Drafts") list = list.filter((entry) => entry.post && ["Ready", "Failed"].includes(entry.status));
    if (view === "Published") list = list.filter((entry) => entry.status === "Published");
    if (view === "Archive") list = list.filter((entry) => ["Skipped", "Archived"].includes(entry.status));
    if (filter !== "All statuses") list = list.filter((entry) => entry.status === filter);
    if (query.trim()) {
      const term = query.toLowerCase();
      list = list.filter((entry) => [entry.title, entry.source, entry.topic, entry.post?.text || ""].some((part) => part.toLowerCase().includes(term)));
    }
    return [...list].sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      if (sort === "source") return a.source.localeCompare(b.source);
      if (sort === "newest" || sort === "oldest") {
        const av = new Date(a.article?.seen_at || a.post?.created_at || 0).getTime();
        const bv = new Date(b.article?.seen_at || b.post?.created_at || 0).getTime();
        return sort === "newest" ? bv - av : av - bv;
      }
      return b.score - a.score;
    });
  }, [all, view, filter, query, sort]);
  const activeEntry = all.find((entry) => entry.key === selected) || null;

  async function action<T>(path: string, body?: unknown, method = "POST", success?: string): Promise<T | null> {
    setWorking(true); setNotice(null);
    try {
      const result = await send<T>(path, body, method);
      await refresh();
      if (success) setNotice(success);
      return result;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The action could not be completed.");
      return null;
    } finally { setWorking(false); }
  }

  async function generate(article: Article) {
    const post = await action<Post>(`/generate/${article.id}`, undefined, "POST", "Draft generated. Open it to review before publishing.");
    if (post) setSelected(`article-${article.id}`);
  }
  async function createIdea() {
    if (idea.trim().length < 10) { setNotice("Enter an idea of at least 10 characters."); return; }
    const post = await action<Post>("/generate/custom", { idea: idea.trim() }, "POST", "Custom draft created.");
    if (post) { setIdea(""); setIdeaOpen(false); setView("Drafts"); setSelected(`post-${post.id}`); }
  }
  async function pause() {
    if (!data) return;
    await action<Automation>("/settings/automation", { ...data.automation, paused: !data.automation.paused }, "PUT", data.automation.paused ? "Autopilot resumed." : "Autopilot paused.");
    setMenu(null);
  }
  async function command(name: string) {
    setPalette(false); setMenu(null);
    if (name === "Create draft") setIdeaOpen(true);
    if (name === "Run discovery") await action("/pipeline/discover", undefined, "POST", "Discovery completed.");
    if (name === "Generate next post") await action("/pipeline/dry-run", undefined, "POST", "Dry run completed; no post was published.");
    if (name === "Open calendar") setView("Calendar");
    if (name === "Open voice settings") router.push("/settings/voice");
    if (name === "Pause autopilot") await pause();
  }

  const automation = data?.automation;
  const newestRun = data?.runs[0];
  return <div className="workspace-page" onClick={() => { if (menu) setMenu(null); }}>
    <header className="workspace-header">
      <div className="title-line"><CalendarDays className="brand-icon" size={30} strokeWidth={2.4} /><h1>Content Calendar</h1></div>
      <p className="page-description">Discover, write, schedule and manage everything your AI content engine publishes.</p>
      <div className="header-secondary"><p>Stories are discovered automatically. Review drafts, adjust your voice, or let autopilot publish for you.</p>
        <button className="autopilot-status" onClick={(event) => { event.stopPropagation(); setMenu(menu === "automation" ? null : "automation"); }}><span className={`live-dot ${automation?.paused ? "paused" : ""}`} />{automation?.paused ? "Autopilot paused" : "Autopilot on"}<ChevronDown size={13} /></button>
      </div>
    </header>

    <div className="views-toolbar">
      <nav aria-label="Database views" className="view-tabs">{views.map(({ name, icon: Icon }) => <button key={name} className={`view-tab ${view === name ? "active" : ""}`} onClick={() => { setView(name); setSelected(null); setFilter("All statuses"); }}><Icon size={15} strokeWidth={view === name ? 2.2 : 1.9} />{name}</button>)}<button className="view-add" title="Create draft" onClick={() => setIdeaOpen(true)}><Plus size={17} /></button></nav>
      <div className="database-controls">
        <div className="control-wrap"><button className={`icon-button ${filter !== "All statuses" ? "selected" : ""}`} title="Filter" aria-label="Filter" onClick={(event) => { event.stopPropagation(); setMenu(menu === "filter" ? null : "filter"); }}><Filter size={16} /></button>{menu === "filter" && <div className="popover compact-popover" onClick={(event) => event.stopPropagation()}><div className="popover-title">Filter by status</div>{["All statuses", ...statusOrder].map((status) => <button key={status} className="popover-option" onClick={() => { setFilter(status); setMenu(null); }}>{status}<span>{filter === status ? <Check size={14} /> : null}</span></button>)}</div>}</div>
        <div className="control-wrap"><button className="icon-button" title="Sort" aria-label="Sort" onClick={(event) => { event.stopPropagation(); setMenu(menu === "sort" ? null : "sort"); }}><ArrowUpDown size={16} /></button>{menu === "sort" && <div className="popover compact-popover" onClick={(event) => event.stopPropagation()}><div className="popover-title">Sort content</div>{([['score','Highest relevance'],['newest','Newest first'],['oldest','Oldest first'],['title','Title A–Z'],['source','Source A–Z']] as [SortKey,string][]).map(([key,label]) => <button key={key} className="popover-option" onClick={() => { setSort(key); setMenu(null); }}>{label}<span>{sort === key ? <Check size={14} /> : null}</span></button>)}</div>}</div>
        <button className="icon-button" title="Automation settings" aria-label="Automation settings" onClick={() => router.push("/settings/automation")}><Zap size={16} /></button>
        <button className="icon-button" title="Search (Ctrl+K)" aria-label="Search" onClick={() => setPalette(true)}><Search size={16} /></button>
        <div className="control-wrap"><button className="icon-button" title="More" aria-label="More" onClick={(event) => { event.stopPropagation(); setMenu(menu === "more" ? null : "more"); }}><MoreHorizontal size={17} /></button>{menu === "more" && <div className="popover compact-popover align-right" onClick={(event) => event.stopPropagation()}><Link href="/settings/voice" className="popover-option">Voice settings</Link><Link href="/settings/sources" className="popover-option">Sources</Link><Link href="/settings/automation" className="popover-option">Automation settings</Link><button className="popover-option" onClick={() => { setMenu(null); refresh().catch((error) => setNotice(error.message)); }}>Refresh content</button></div>}</div>
        <div className="control-wrap"><button className="new-button" onClick={(event) => { event.stopPropagation(); setMenu(menu === "new" ? null : "new"); }}>New <ChevronDown size={14} /></button>{menu === "new" && <div className="popover compact-popover align-right" onClick={(event) => event.stopPropagation()}><button className="popover-option" onClick={() => { setMenu(null); setIdeaOpen(true); }}><SquarePen size={14} />Create draft</button><button className="popover-option" onClick={() => command("Run discovery")}><CircleDot size={14} />Run discovery</button><button className="popover-option" onClick={() => command("Generate next post")}><WandSparkles size={14} />Generate next post</button></div>}</div>
      </div>
    </div>

    {notice && <div className="inline-notice" role="status"><span>{notice}</span><button onClick={() => setNotice(null)} aria-label="Dismiss"><X size={14} /></button></div>}
    {newestRun?.status === "failed" && !notice && <div className="inline-notice subtle-error"><span>Last run: {newestRun.detail}</span><button onClick={() => command("Run discovery")}>Retry discovery</button></div>}
    {query && !palette && <div className="active-search"><Search size={13} /> Searching for “{query}” <button onClick={() => setQuery("")}><X size={13} /> Clear</button></div>}

    <main>
      {view === "Calendar" ? <CalendarView entries={all} month={month} setMonth={setMonth} zone={automation?.timezone || "America/New_York"} onOpen={(entry) => setSelected(entry.key)} /> :
        view === "By status" ? <div className="grouped-view">{statusOrder.map((status) => { const group = filtered.filter((entry) => entry.status === status); return group.length ? <section key={status} className="status-group"><div className="group-heading"><ChevronDown size={14} />{status.toUpperCase()} <span>{group.length}</span></div><DatabaseTable entries={group} view="All content" zone={automation?.timezone} onOpen={(entry) => setSelected(entry.key)} onGenerate={generate} busy={working} /></section> : null; })}</div> :
        loading ? <><TableHeader view={view} /><SkeletonRows /></> :
        filtered.length ? <DatabaseTable entries={filtered} view={view} zone={automation?.timezone} onOpen={(entry) => setSelected(entry.key)} onGenerate={generate} busy={working} /> :
        <div className="empty-state"><strong>{view === "Drafts" ? "No drafts yet." : view === "Published" ? "No published posts yet." : view === "Discover" ? "No discovered stories in this view." : "No content in this view."}</strong><p>{view === "Drafts" ? "Stories selected by your content engine will appear here." : "Try another view or run discovery."}</p><button onClick={() => command("Run discovery")}>Discover stories</button></div>}
    </main>
    <div className="table-footer"><span>{filtered.length} {filtered.length === 1 ? "item" : "items"}</span><span>{working ? <><Loader2 size={12} className="spin" /> Working</> : automation?.dry_run ? "Dry run · publishing protected" : "Live publishing enabled"}</span></div>

    {menu === "automation" && automation && <div className="popover automation-popover" onClick={(event) => event.stopPropagation()}><div className="popover-title">{automation.paused ? "Autopilot is paused" : "Autopilot is running"}</div><p>Next posting windows: {automation.post_times.join(", ")} · {automation.timezone}</p><p>Stories waiting: {all.filter((entry) => entry.status === "Discovered").length}</p><p className="popover-note">{automation.dry_run ? "Dry run is on. Nothing can publish." : automation.publish_without_approval ? "Automatic publishing is enabled." : "Publishing needs your approval."}</p><button className="popover-option popover-strong" onClick={pause}>{automation.paused ? <Play size={14} /> : <Pause size={14} />}{automation.paused ? "Resume autopilot" : "Pause autopilot"}</button><Link className="popover-option" href="/settings/automation"><Settings2 size={14} />Automation settings</Link></div>}

    {activeEntry && <Inspector key={`${activeEntry.key}-${activeEntry.post?.id || 0}`} entry={activeEntry} automation={automation} busy={working} onClose={() => setSelected(null)} onAction={action} onGenerate={generate} onRefresh={refresh} />}
    {ideaOpen && <div className="modal-backdrop" onMouseDown={() => setIdeaOpen(false)}><div className="idea-modal" role="dialog" aria-modal="true" aria-label="Create a draft" onMouseDown={(event) => event.stopPropagation()}><div className="modal-head"><h2>Create a draft</h2><button className="icon-button" onClick={() => setIdeaOpen(false)}><X size={18} /></button></div><p>Start with an idea in your own words. The same voice profile will shape the draft.</p><textarea autoFocus value={idea} onChange={(event) => setIdea(event.target.value)} placeholder="What have you been thinking about?" /><div className="modal-actions"><button className="text-button" onClick={() => setIdeaOpen(false)}>Cancel</button><button className="blue-button" disabled={working} onClick={createIdea}>{working ? "Generating…" : "Generate draft"}</button></div></div></div>}
    {palette && <div className="modal-backdrop" onMouseDown={() => setPalette(false)}><div className="command-palette" role="dialog" aria-modal="true" aria-label="Search workspace" onMouseDown={(event) => event.stopPropagation()}><div className="palette-search"><Search size={18} /><input autoFocus placeholder="Search stories, posts, sources or commands…" value={query} onChange={(event) => setQuery(event.target.value)} /><span>ESC</span></div><div className="palette-results"><div className="palette-label">Commands</div>{["Create draft", "Run discovery", "Generate next post", "Open calendar", "Open voice settings", "Pause autopilot"].filter((item) => item.toLowerCase().includes(query.toLowerCase())).map((item) => <button key={item} onClick={() => command(item)}><Zap size={14} />{item}</button>)}<div className="palette-label">Content</div>{all.filter((entry) => [entry.title, entry.source, entry.topic, entry.post?.text || ""].some((text) => text.toLowerCase().includes(query.toLowerCase()))).slice(0, 8).map((entry) => <button key={entry.key} onClick={() => { setSelected(entry.key); setPalette(false); }}><FilePenLine size={14} /><span className="truncate">{entry.title}</span><small>{entry.source}</small></button>)}</div></div></div>}
  </div>;
}

function TableHeader({ view }: { view: View }) {
  const discover = view === "Discover";
  const published = view === "Published";
  const draft = view === "Drafts";
  const columns = discover ? ["STORY", "SOURCE", "PUBLISHED", "TOPIC", "RELEVANCE", "REASON", "ACTION"] :
    published ? ["POST", "SOURCE", "PUBLISHED", "TOPIC", "VOICE", "X LINK", "STATUS"] :
    draft ? ["POST", "SOURCE", "VOICE", "CREATED", "STATUS", "SCHEDULED", "ACTION"] :
    ["STORY / POST", "SOURCE", "STATUS", "PUBLISH DATE", "TOPIC", "VOICE", "RELEVANCE", "ACTION"];
  return <div className={`db-grid db-${view.toLowerCase().replace(/\s/g, "-")} db-head`}>{columns.map((name) => <div className="db-cell" key={name}>{name === "PUBLISH DATE" || name === "PUBLISHED" || name === "SCHEDULED" ? <CalendarDays size={13} /> : null}{name}</div>)}</div>;
}

function DatabaseTable({ entries: rows, view, zone, onOpen, onGenerate, busy }: { entries: Entry[]; view: View; zone?: string; onOpen: (entry: Entry) => void; onGenerate: (article: Article) => void; busy: boolean }) {
  const discover = view === "Discover"; const published = view === "Published"; const draft = view === "Drafts";
  return <div className="database-scroll"><div className="database-table"><TableHeader view={view} />{rows.map((entry) => <div className={`db-grid db-${view.toLowerCase().replace(/\s/g, "-")} db-row`} key={entry.key} onClick={() => onOpen(entry)} tabIndex={0} role="button" onKeyDown={(event) => { if (event.key === "Enter") onOpen(entry); }}>
    <div className="db-cell title-cell"><FilePenLine size={15} className="row-icon" /><span title={entry.title} className="truncate">{entry.title}</span></div>
    <div className="db-cell source-cell truncate">{entry.source}</div>
    {discover ? <><div className="db-cell date-cell">{entry.article ? relativeDate(entry.article.published_at) : "—"}</div><div className="db-cell"><TopicTag value={entry.topic} /></div><div className="db-cell relevance-cell" title="Based on your interests, source quality, recency and topic history.">{entry.score}%</div><div className="db-cell reason-cell truncate" title={entry.article?.reason}>{entry.article?.reason?.split(",")[1]?.trim() || "Matches your interests"}</div><div className="db-cell action-cell"><button disabled={busy} onClick={(event) => { event.stopPropagation(); if (entry.article) onGenerate(entry.article); }}>Generate →</button></div></> :
    published ? <><div className="db-cell date-cell">{dateLabel(entry.post?.published_at || null, zone)}</div><div className="db-cell"><TopicTag value={entry.topic} /></div><div className="db-cell"><VoiceTag value={entry.style} /></div><div className="db-cell">{entry.post?.publisher_response?.provider === "x" && entry.post?.publisher_response?.post_id ? <a onClick={(event) => event.stopPropagation()} href={`https://x.com/i/web/status/${entry.post.publisher_response.post_id}`} target="_blank" rel="noreferrer" className="subtle-link">View ↗</a> : <span className="muted-dash">—</span>}</div><div className="db-cell"><StatusTag value={entry.status} /></div></> :
    draft ? <><div className="db-cell"><VoiceTag value={entry.style} /></div><div className="db-cell date-cell">{dateLabel(entry.post?.created_at || null, zone)}</div><div className="db-cell"><StatusTag value={entry.status} /></div><div className="db-cell date-cell">{dateLabel(entry.post?.scheduled_at || null, zone)}</div><div className="db-cell action-cell"><button onClick={(event) => { event.stopPropagation(); onOpen(entry); }}>Edit →</button></div></> :
    <><div className="db-cell"><StatusTag value={entry.status} /></div><div className="db-cell date-cell">{dateLabel(entry.date, zone)}</div><div className="db-cell"><TopicTag value={entry.topic} /></div><div className="db-cell"><VoiceTag value={entry.style} /></div><div className="db-cell relevance-cell" title="Based on your interests, source quality, recency and topic history.">{entry.score ? `${entry.score}%` : "—"}</div><div className="db-cell action-cell"><button onClick={(event) => { event.stopPropagation(); if (entry.article && !entry.post) onGenerate(entry.article); else onOpen(entry); }}>{entry.post ? "Edit" : "Generate"}</button><MoreHorizontal size={15} /></div></>}
  </div>)}</div></div>;
}

function Inspector({ entry, automation, busy, onClose, onAction, onGenerate, onRefresh }: { entry: Entry; automation?: Automation; busy: boolean; onClose: () => void; onAction: <T>(path: string, body?: unknown, method?: string, success?: string) => Promise<T | null>; onGenerate: (article: Article) => void; onRefresh: () => Promise<void> }) {
  const [text, setText] = useState(entry.post?.text || "");
  const [style, setStyle] = useState(entry.post?.style || "builder_perspective");
  const [schedule, setSchedule] = useState("");
  const [showSchedule, setShowSchedule] = useState(false);
  const article = entry.article; const post = entry.post;
  const editable = !!post && !["published", "queued"].includes(post.status);
  async function save() { if (post) await onAction<Post>(`/posts/${post.id}`, { text, style }, "PATCH", "Draft saved."); }
  async function schedulePost() {
    if (!post || !schedule) return;
    const when = new Date(schedule);
    if (Number.isNaN(when.getTime())) return;
    if (text !== post.text || style !== post.style) {
      const saved = await onAction<Post>(`/posts/${post.id}`, { text, style }, "PATCH");
      if (!saved) return;
    }
    const result = await onAction<Post>(`/posts/${post.id}/schedule`, { scheduled_at: when.toISOString() }, "POST", "Post scheduled.");
    if (result) setShowSchedule(false);
  }
  async function publish() {
    if (!post) return;
    if (text !== post.text || style !== post.style) {
      const saved = await onAction<Post>(`/posts/${post.id}`, { text, style }, "PATCH");
      if (!saved) return;
    }
    await onAction<Post>(`/publish/${post.id}`, undefined, "POST", "Post sent to publisher.");
  }
  return <><div className="inspector-scrim" onClick={onClose} /><aside className="inspector" aria-label="Content inspector"><div className="inspector-top"><span>{post ? "POST" : "ARTICLE"}</span><button className="icon-button" aria-label="Close inspector" onClick={onClose}><X size={18} /></button></div>
    <div className="inspector-scroll"><h2>{article?.title || "Custom draft"}</h2><div className="inspector-meta">{entry.source}{article?.published_at ? ` · ${relativeDate(article.published_at)}` : ""}</div><div className="inspector-tags"><TopicTag value={entry.topic} />{post ? <StatusTag value={entry.status} /> : null}</div>
    {article && <><section className="inspector-section"><h3>Why this was selected</h3><div className="relevance-large">{Math.min(100, Math.round(article.score))}% <span>relevance score</span></div><ul>{article.reason.split(",").filter(Boolean).map((reason, index) => <li key={index}>{reason.trim()}</li>)}</ul></section><section className="inspector-section"><h3>Source summary</h3><p>{article.description || "This feed did not provide a summary. Open the source to inspect the story before generating a post."}</p><a className="source-link" href={article.url} target="_blank" rel="noreferrer">View original <ExternalLink size={13} /></a></section></>}
    {post ? <section className="inspector-section editor-section"><h3>Generated post</h3><textarea className="post-editor" aria-label="Edit post" value={text} readOnly={!editable} onChange={(event) => setText(event.target.value)} /><div className={`character-count ${postLength(text) > 280 ? "over" : ""}`}>{postLength(text)} / 280</div><div className="editor-properties"><div><span>Source</span><strong>{entry.source}</strong></div><div><span>Topic</span><TopicTag value={entry.topic} /></div><div><span>Voice</span>{editable ? <select value={style} onChange={(event) => setStyle(event.target.value)}>{styles.map((item) => <option key={item} value={item}>{voiceLabel(item)}</option>)}</select> : <VoiceTag value={style} />}</div><div><span>Schedule</span><strong>{dateLabel(post.scheduled_at, automation?.timezone)}</strong></div></div>{post.failure_reason && <p className="field-error">{post.failure_reason}</p>}</section> : <section className="inspector-section"><h3>Generated post</h3><p className="muted-copy">No draft yet. Generate one using your voice profile and this source.</p></section>}
    {post && <section className="inspector-section feedback-section"><h3>Writing feedback</h3><div className="feedback-actions"><button className={post.feedback === "like" ? "chosen" : ""} onClick={() => onAction(`/posts/${post.id}/feedback`, { rating: "like", reason: "good_voice" }, "POST", "Feedback saved.")}>✓ Like</button><button className={post.feedback === "dislike" ? "chosen" : ""} onClick={() => onAction(`/posts/${post.id}/feedback`, { rating: "dislike", reason: "too_generic" }, "POST", "Feedback saved.")}>× Too generic</button></div></section>}
    {article && !post && <button className="text-button" disabled={busy} onClick={() => onAction(`/articles/${article.id}`, { skipped: !article.skipped }, "PATCH", article.skipped ? "Story restored." : "Story skipped.")}>{article.skipped ? "Restore story" : "Skip story"}</button>}
    {showSchedule && editable && <div className="schedule-box"><label htmlFor="schedule-at">Publish date and time</label><input id="schedule-at" type="datetime-local" value={schedule} onChange={(event) => setSchedule(event.target.value)} /><small>Uses your computer&apos;s local time; stored as UTC.</small><div><button className="text-button" onClick={() => setShowSchedule(false)}>Cancel</button><button className="blue-button" disabled={!schedule || busy} onClick={schedulePost}>Confirm schedule</button></div></div>}
    </div><div className="inspector-footer">{!post && article ? <button className="blue-button" disabled={busy || article.skipped} onClick={() => onGenerate(article)}><WandSparkles size={14} />Generate post</button> : null}{post && editable ? <><button className="text-button" disabled={busy || !article} onClick={async () => { if (post) { const replacement = await onAction<Post>(`/posts/${post.id}/regenerate`, undefined, "POST", "New draft generated."); if (replacement) await onRefresh(); } }}><RotateCw size={14} />Regenerate</button><button className="text-button" disabled={busy} onClick={save}><Save size={14} />Save</button><button className="text-button" disabled={busy} onClick={() => setShowSchedule(true)}><Clock3 size={14} />Schedule</button><button className="blue-button" disabled={busy || automation?.dry_run} title={automation?.dry_run ? "DRY_RUN=true protects publishing" : "Publish this post"} onClick={publish}>Publish</button></> : null}{post?.status === "scheduled" ? <button className="text-button" disabled={busy} onClick={() => onAction(`/posts/${post.id}/unschedule`, undefined, "POST", "Post unscheduled.")}>Unschedule</button> : null}{automation?.dry_run && post && <span className="footer-note">Dry run is on</span>}</div></aside></>;
}

function CalendarView({ entries: all, month, setMonth, zone, onOpen }: { entries: Entry[]; month: Date; setMonth: (value: Date) => void; zone: string; onOpen: (entry: Entry) => void }) {
  const year = month.getFullYear(); const monthIndex = month.getMonth();
  const first = new Date(year, monthIndex, 1).getDay();
  const count = new Date(year, monthIndex + 1, 0).getDate();
  const cells = Array.from({ length: Math.ceil((first + count) / 7) * 7 }, (_, index) => index - first + 1);
  const scheduled = all.filter((entry) => entry.date && ["Scheduled", "Published"].includes(entry.status));
  const keyFor = (value: Date) => (() => { const parts = new Intl.DateTimeFormat("en-US", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: zone }).formatToParts(value); const get = (type: string) => parts.find((part) => part.type === type)?.value || ""; return `${get("year")}-${get("month")}-${get("day")}`; })();
  return <div className="calendar-view"><div className="calendar-toolbar"><strong>{new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(month)}</strong><div><button className="icon-button" aria-label="Previous month" onClick={() => setMonth(new Date(year, monthIndex - 1, 1))}><ChevronLeft size={17} /></button><button className="calendar-today" onClick={() => setMonth(new Date())}>Today</button><button className="icon-button" aria-label="Next month" onClick={() => setMonth(new Date(year, monthIndex + 1, 1))}><ChevronRight size={17} /></button></div></div><div className="calendar-grid">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <div className="calendar-weekday" key={day}>{day}</div>)}{cells.map((day, index) => { const inMonth = day >= 1 && day <= count; const date = new Date(year, monthIndex, day); const targetKey = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`; const items = scheduled.filter((entry) => keyFor(instant(entry.date!)) === targetKey); return <div className={`calendar-day ${inMonth ? "" : "outside"}`} key={index}><span>{date.getDate()}</span>{items.map((entry) => <button className="calendar-item" title={entry.title} key={entry.key} onClick={() => onOpen(entry)}><small>{new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: zone }).format(instant(entry.date!))}</small><span>{entry.post?.text.split("\n")[0] || entry.title}</span></button>)}</div>; })}</div></div>;
}
