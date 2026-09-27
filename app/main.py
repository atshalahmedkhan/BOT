from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .config import settings
from .database import Article, Post, Run, SessionLocal, init_db
from .service import run_pipeline, generate_for_article, publish_post
from .ai import AIClient
from .validation import x_length
from .workspace import router as workspace_router
import re

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app=FastAPI(title='Personal X News Bot',lifespan=lifespan)
app.include_router(workspace_router)

def item(x):
    d={k:v for k,v in vars(x).items() if not k.startswith('_')}
    return d

@app.get('/health')
def health(): return {'status':'ok','dry_run':settings.dry_run}

@app.get('/articles')
def articles(limit:int=50):
    with SessionLocal() as db: return [item(x) for x in db.scalars(select(Article).order_by(Article.id.desc()).limit(min(limit,200))).all()]

@app.get('/posts')
def posts(limit:int=50):
    with SessionLocal() as db: return [item(x) for x in db.scalars(select(Post).order_by(Post.id.desc()).limit(min(limit,200))).all()]

@app.get('/runs')
def runs(limit:int=50):
    with SessionLocal() as db: return [item(x) for x in db.scalars(select(Run).order_by(Run.id.desc()).limit(min(limit,200))).all()]

@app.get('/stats')
def stats():
    with SessionLocal() as db:
        return {'articles':db.scalar(select(func.count(Article.id))),'posts_generated':db.scalar(select(func.count(Post.id))),'posts_published':db.scalar(select(func.count(Post.id)).where(Post.status=='published')),'posts_queued':db.scalar(select(func.count(Post.id)).where(Post.status=='queued')),'ai_calls':db.scalar(select(func.coalesce(func.sum(Run.ai_calls),0))),'input_tokens':db.scalar(select(func.coalesce(func.sum(Run.input_tokens),0))),'output_tokens':db.scalar(select(func.coalesce(func.sum(Run.output_tokens),0))),'estimated_cost':db.scalar(select(func.sum(Run.estimated_cost)))}

@app.post('/pipeline/run')
def pipeline_run(): return run_pipeline()
@app.post('/pipeline/dry-run')
def pipeline_dry_run(): return run_pipeline(dry_run=True)

@app.post('/generate/{article_id}')
def generate_article(article_id:int):
    with SessionLocal() as db:
        a=db.get(Article,article_id)
        if not a: raise HTTPException(404,'article not found')
        run=Run(detail='Manual article generation');db.add(run);db.commit()
        try:
            post=generate_for_article(db,a,run);run.status=post.status;db.commit();return item(post)
        except Exception as exc:
            run.status='failed';run.detail=str(exc);db.commit();raise HTTPException(503,str(exc)) from exc

class CustomIdea(BaseModel):
    idea: str=Field(min_length=10,max_length=1000)

@app.post('/generate/custom')
def custom(idea:CustomIdea):
    story={'title':idea.idea,'headline':idea.idea,'description':'User supplied idea; no external facts or source URL.','source':'user','publication_date':None,'url':'','category':'manual'}
    with SessionLocal() as db:
        run=Run(detail='Custom idea generation',ai_calls=1);db.add(run);db.commit()
        try:
            generated,input_tokens,output_tokens=AIClient().generate(story)
            run.input_tokens=input_tokens;run.output_tokens=output_tokens
            if settings.input_cost_per_million is not None and settings.output_cost_per_million is not None:
                run.estimated_cost=(input_tokens*settings.input_cost_per_million+output_tokens*settings.output_cost_per_million)/1_000_000
            run.status='generated';db.commit()
        except Exception as exc:
            run.status='failed';run.detail=str(exc);db.commit();raise HTTPException(503,str(exc)) from exc
    if x_length(generated.post)>280: raise HTTPException(422,'generated post exceeds X limit')
    if generated.confidence<.65 or re.search(r'\bI (tried|tested|used|attended|spoke|met|visited|built|saw)\b',generated.post,re.I): raise HTTPException(422,'custom post failed validation')
    if len(re.findall(r'(?<!\w)#\w+',generated.post))>2: raise HTTPException(422,'too many hashtags')
    with SessionLocal() as db:
        from difflib import SequenceMatcher
        if any(SequenceMatcher(None,generated.post,p.text).ratio()>.82 for p in db.scalars(select(Post).order_by(Post.id.desc()).limit(50)).all()): raise HTTPException(422,'similar post already exists')
        post=Post(text=generated.post,style=generated.style,confidence=generated.confidence,factual_claims=generated.factual_claims,status='generated')
        db.add(post);db.commit();db.refresh(post)
        return item(post)

class Feedback(BaseModel):
    rating: str
    reason: str | None=None

@app.post('/posts/{post_id}/feedback')
def feedback(post_id:int,body:Feedback):
    if body.rating not in {'like','dislike'}: raise HTTPException(422,'rating must be like or dislike')
    if body.reason not in {None,'too_generic','too_formal','too_long','too_hype','good_voice','good_insight','bad_topic'}: raise HTTPException(422,'invalid reason')
    with SessionLocal() as db:
        p=db.get(Post,post_id)
        if not p: raise HTTPException(404,'post not found')
        p.feedback=body.rating;p.feedback_reason=body.reason;db.commit();db.refresh(p)
        return item(p)

@app.post('/publish/{post_id}')
def publish(post_id:int):
    with SessionLocal() as db:
        p=db.get(Post,post_id)
        if not p: raise HTTPException(404,'post not found')
        try: return item(publish_post(db,p))
        except Exception as exc: raise HTTPException(409,str(exc)) from exc
