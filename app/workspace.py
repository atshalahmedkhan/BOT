"""Small persistence and editing API for the editorial workspace."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import json
import re
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from .config import ROOT, settings
from .database import Article, Post, Run, WorkspaceSetting, SessionLocal, now
from .news import fetch_stories, duplicate, score_story
from .personalization import interests
from .service import generate_for_article, topic_for, publish_post
from .validation import x_length

router = APIRouter()
VOICE_PATH = ROOT / 'VOICE_PROFILE.md'
EXAMPLES_PATH = ROOT / 'data/style_examples.json'
SOURCES_PATH = ROOT / 'config/sources.yaml'

def record(row): return {key: value for key, value in vars(row).items() if not key.startswith('_')}

def automation(db):
    row = db.get(WorkspaceSetting, 'automation')
    return row.value if row else {
        'paused': False, 'discover': True, 'generate': True,
        'publish_without_approval': False,
        'post_times': settings.post_times.split(','),
        'timezone': settings.timezone, 'minimum_relevance': settings.min_score,
    }

class AutomationUpdate(BaseModel):
    paused: bool = False
    discover: bool = True
    generate: bool = True
    publish_without_approval: bool = False
    post_times: list[str] = Field(min_length=1, max_length=6)
    timezone: str
    minimum_relevance: float = Field(ge=0, le=100)

@router.get('/settings/automation')
def get_automation():
    with SessionLocal() as db: return {**automation(db), 'dry_run': settings.dry_run}

@router.put('/settings/automation')
def put_automation(body: AutomationUpdate):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try: ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError: raise HTTPException(422, 'Unknown timezone')
    for value in body.post_times:
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value): raise HTTPException(422, 'Times must use HH:MM')
    with SessionLocal() as db:
        row = db.get(WorkspaceSetting, 'automation')
        if not row: row = WorkspaceSetting(key='automation', value={}); db.add(row)
        row.value = body.model_dump(); db.commit()
        return {**row.value, 'dry_run': settings.dry_run}

class VoiceUpdate(BaseModel):
    description: str = Field(min_length=20, max_length=10000)
    examples: list[str] = Field(max_length=50)

@router.get('/settings/voice')
def get_voice():
    return {'description': VOICE_PATH.read_text(encoding='utf-8'), 'examples': [x['text'] for x in json.loads(EXAMPLES_PATH.read_text(encoding='utf-8'))]}

@router.put('/settings/voice')
def put_voice(body: VoiceUpdate):
    cleaned = [example.strip() for example in body.examples if example.strip()]
    VOICE_PATH.write_text(body.description.strip() + '\n', encoding='utf-8')
    EXAMPLES_PATH.write_text(json.dumps([{'text': text} for text in cleaned], indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return {'description': body.description.strip(), 'examples': cleaned}

class SourceInput(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    url: HttpUrl
    category: str = Field(min_length=2, max_length=100)
    priority: int = Field(ge=1, le=5)
    enabled: bool = True

class SourcesUpdate(BaseModel):
    sources: list[SourceInput] = Field(max_length=100)

@router.get('/settings/sources')
def get_sources(): return yaml.safe_load(SOURCES_PATH.read_text(encoding='utf-8'))

@router.put('/settings/sources')
def put_sources(body: SourcesUpdate):
    rows = [{**row.model_dump(), 'url': str(row.url)} for row in body.sources]
    if len({row['name'].lower() for row in rows}) != len(rows): raise HTTPException(422, 'Source names must be unique')
    SOURCES_PATH.write_text(yaml.safe_dump({'sources': rows}, sort_keys=False, allow_unicode=True), encoding='utf-8')
    return {'sources': rows}

def discover():
    with SessionLocal() as db:
        run = Run(detail='Discovery only'); db.add(run); db.commit()
        try:
            stories, errors = fetch_stories(); run.stories_fetched = len(stories)
            existing = db.scalars(select(Article).order_by(Article.id.desc()).limit(1000)).all()
            recent_posts = db.scalars(select(Post).where(Post.status.in_(['published','queued'])).order_by(Post.id.desc()).limit(20)).all()
            added = 0
            for story in stories:
                if duplicate(story, existing): continue
                score, reason = score_story(story, interests(), recent_posts)
                row = Article(title=story['title'], description=story['description'], url=story['url'], normalized_title=story['normalized_title'], source=story['source'], category=story['category'], published_at=story['published_at'], score=score, reason=reason, topic=topic_for(story))
                db.add(row); existing.append(row); added += 1
            run.status='completed';run.detail=f'{added} new stories';db.commit()
            return {'stories_fetched': len(stories), 'added': added, 'feed_errors': errors, 'run_id': run.id}
        except Exception as exc:
            run.status='failed';run.detail=str(exc);db.commit()
            raise HTTPException(503, str(exc)) from exc

@router.post('/pipeline/discover')
def discover_endpoint(): return discover()

class ArticleUpdate(BaseModel):
    skipped: bool

@router.patch('/articles/{article_id}')
def update_article(article_id: int, body: ArticleUpdate):
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if not article: raise HTTPException(404, 'Article not found')
        article.skipped = body.skipped;db.commit();db.refresh(article)
        return record(article)

class PostUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    style: Literal['reaction','explanation','builder_perspective','question','straightforward']

def check_edit(post, text):
    if x_length(text) > 280: raise HTTPException(422, 'Post exceeds X character limit')
    if post.article and post.article.url not in text: raise HTTPException(422, 'Source URL must remain in post')
    if re.search(r"\b(I|we)\s+(tried|tested|used|attended|spoke|met|visited|built|saw)\b|\b(I've|we've)\s+(tried|tested|used|attended|spoken|met|visited|built|seen)\b", text, re.I):
        raise HTTPException(422, 'Unsupported personal experience')

@router.patch('/posts/{post_id}')
def update_post(post_id: int, body: PostUpdate):
    with SessionLocal() as db:
        post=db.get(Post, post_id)
        if not post: raise HTTPException(404, 'Post not found')
        if post.status in {'published','queued'}: raise HTTPException(409, 'Published or queued posts cannot be edited')
        check_edit(post, body.text)
        post.text=body.text.strip();post.style=body.style
        if post.status in {'failed','archived'}: post.status='generated';post.failure_reason=''
        db.commit();db.refresh(post);return record(post)

class ScheduleInput(BaseModel):
    scheduled_at: datetime

@router.post('/posts/{post_id}/schedule')
def schedule_post(post_id: int, body: ScheduleInput):
    when = body.scheduled_at
    if when.tzinfo is None: raise HTTPException(422, 'Schedule needs a timezone offset')
    if when <= now(): raise HTTPException(422, 'Schedule must be in the future')
    with SessionLocal() as db:
        post=db.get(Post,post_id)
        if not post: raise HTTPException(404, 'Post not found')
        if post.status not in {'generated','scheduled'}: raise HTTPException(409, 'Only valid drafts can be scheduled')
        check_edit(post,post.text)
        post.scheduled_at=when.astimezone(timezone.utc);post.status='scheduled'
        db.commit();db.refresh(post);return record(post)

@router.post('/posts/{post_id}/unschedule')
def unschedule_post(post_id: int):
    with SessionLocal() as db:
        post=db.get(Post,post_id)
        if not post: raise HTTPException(404, 'Post not found')
        if post.status!='scheduled': raise HTTPException(409, 'Post is not scheduled')
        post.status='generated';post.scheduled_at=None;db.commit();db.refresh(post);return record(post)

@router.post('/posts/{post_id}/regenerate')
def regenerate(post_id: int):
    with SessionLocal() as db:
        post=db.get(Post,post_id)
        if not post: raise HTTPException(404, 'Post not found')
        if not post.article: raise HTTPException(422, 'Custom ideas cannot be regenerated from a source')
        if post.status in {'published','queued'}: raise HTTPException(409, 'Published posts cannot be regenerated')
        run=Run(detail='Regenerate post');db.add(run);db.commit()
        try:
            replacement=generate_for_article(db,post.article,run,exclude_post_id=post.id)
            if replacement.status=='generated': post.status='archived'
            run.status=replacement.status;db.commit()
            return record(replacement)
        except Exception as exc:
            run.status='failed';run.detail=str(exc);db.commit()
            raise HTTPException(503,str(exc)) from exc

@router.get('/workspace')
def workspace():
    with SessionLocal() as db:
        return {
            'articles':[record(row) for row in db.scalars(select(Article).order_by(Article.id.desc()).limit(500)).all()],
            'posts':[record(row) for row in db.scalars(select(Post).order_by(Post.id.desc()).limit(300)).all()],
            'runs':[record(row) for row in db.scalars(select(Run).order_by(Run.id.desc()).limit(20)).all()],
            'automation':{**automation(db),'dry_run':settings.dry_run},
        }
