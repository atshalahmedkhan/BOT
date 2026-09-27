import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import feedparser
import httpx
import yaml
from .config import ROOT

def clean_text(s): return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()
def norm_title(s): return re.sub(r'[^a-z0-9 ]', '', clean_text(s).lower())
def norm_url(url):
    p = urlsplit(url.strip())
    query = urlencode([(k,v) for k,v in parse_qsl(p.query) if not (k.lower().startswith('utm_') or k.lower() in {'fbclid','gclid','ref'})])
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix('www.'), p.path.rstrip('/') or '/', query, ''))

def parse_feed(body, source):
    parsed = feedparser.parse(body)
    out = []
    for e in parsed.entries[:50]:
        title, url = clean_text(e.get('title')), e.get('link', '')
        if not title or not url.startswith(('https://','http://')): continue
        stamp = e.get('published_parsed') or e.get('updated_parsed')
        published = datetime(*stamp[:6], tzinfo=timezone.utc) if stamp else None
        if published and published < datetime.now(timezone.utc)-timedelta(days=7): continue
        out.append(dict(title=title, description=clean_text(e.get('summary',''))[:1000], url=norm_url(url), normalized_title=norm_title(title), source=source['name'], category=source['category'], priority=int(source.get('priority', 1)), published_at=published))
    return out

def fetch_stories():
    sources = yaml.safe_load((ROOT/'config/sources.yaml').read_text(encoding='utf-8'))['sources']
    stories, errors = [], []
    with httpx.Client(timeout=15, follow_redirects=True, headers={'User-Agent':'PersonalNewsBot/1.0'}) as client:
        for source in sources:
            if not source.get('enabled', True): continue
            try:
                r = client.get(source['url']); r.raise_for_status()
                stories.extend(parse_feed(r.content, source))
            except (httpx.HTTPError, ValueError) as exc: errors.append(f"{source['name']}: {exc}")
    return stories, errors

def similar(a,b): return SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()
def idea_similar(a,b):
    stop={'the','a','an','in','on','for','to','of','and','with','from','new','says','announces','launches','reveals'}
    x=set(norm_title(a).split())-stop; y=set(norm_title(b).split())-stop
    return len(x & y)/len(x | y) if x and y else 0
def duplicate(story, others):
    return any(story['url'] == x.url or similar(story['title'], x.title) >= .86 or idea_similar(story['title'],x.title)>=.72 for x in others)

def score_story(story, interests, recent_posts):
    age = (datetime.now(timezone.utc) - story['published_at']).total_seconds()/3600 if story['published_at'] else 72
    if age > 168: return 0, 'older than seven days'
    category = story['category'].lower()
    group = next((g for g in ('high_priority','medium_priority','low_priority') if category in [x.lower() for x in interests.get(g,[])]), None)
    base = {'high_priority':28,'medium_priority':14,'low_priority':-10,None:0}[group]
    hay = (story['title']+' '+story['description']).lower()
    keyword = min(20, sum(8 for x in interests.get('keywords',{}).get('high',[]) if x.lower() in hay) + sum(3 for x in interests.get('keywords',{}).get('medium',[]) if x.lower() in hay))
    penalty = sum(8 for x in interests.get('keywords',{}).get('low',[]) if x.lower() in hay)
    topic = next((x.lower() for x in interests.get('keywords',{}).get('high',[]) if x.lower() in hay), category)
    repeated = sum(1 for p in recent_posts if p.article and (p.article.topic == topic or p.article.category == category))
    score = max(0, 25 - age/6) + base + keyword + 2*story['priority'] + 5 - penalty - min(30, 10*repeated)
    return round(score, 1), f'recent ({age:.0f}h), {group or "unlisted"} category, source priority {story["priority"]}, topic {topic}, {repeated} recent related posts'
