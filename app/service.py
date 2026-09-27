from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .ai import AIClient, MissingCredential
from .config import settings
from .database import Article, Post, Run, WorkspaceSetting, SessionLocal, now
from .news import fetch_stories, duplicate, score_story
from .personalization import interests, feedback_signals
from .publishing import publisher
from .validation import validate_post, x_length
from .config import ROOT
import yaml

def topic_for(story):
    hay=(story['title']+' '+story['description']).lower()
    return next((x.lower() for x in interests().get('keywords',{}).get('high',[]) if x.lower() in hay),story['category'].lower())

def story_data(a):
    return {'headline':a.title,'description':a.description,'source':a.source,'publication_date':a.published_at.isoformat() if a.published_at else None,'url':a.url,'category':a.category,'title':a.title}

def generate_for_article(db, article, run=None, ai=None, exclude_post_id=None):
    recent=[p for p in db.scalars(select(Post).order_by(Post.id.desc()).limit(50)).all() if p.id != exclude_post_id][:30]
    feedback=feedback_signals(recent)
    if run: run.ai_calls+=1; db.commit()
    model, in_tokens, out_tokens=(ai or AIClient()).generate(story_data(article),feedback)
    if run:
        run.input_tokens+=in_tokens; run.output_tokens+=out_tokens
        if settings.input_cost_per_million is not None and settings.output_cost_per_million is not None:
            run.estimated_cost=(run.estimated_cost or 0)+(in_tokens*settings.input_cost_per_million+out_tokens*settings.output_cost_per_million)/1_000_000
    errors, full=validate_post(model,article,recent)
    post=Post(article_id=article.id,text=full,style=model.style,confidence=model.confidence,factual_claims=model.factual_claims,status='failed' if errors else 'generated',failure_reason='; '.join(errors))
    db.add(post); db.commit(); db.refresh(post)
    return post

def publish_post(db, post, force=False):
    if settings.dry_run: raise RuntimeError('DRY_RUN=true blocks all publishing')
    if post.status not in {'generated','scheduled'}: raise ValueError('Only validated drafts or scheduled posts can publish')
    if not post.text.strip() or x_length(post.text)>280: raise ValueError('Post is empty or over X character limit')
    if post.article and post.article.url not in post.text: raise ValueError('Source URL missing from post')
    from zoneinfo import ZoneInfo
    local_day=now().astimezone(ZoneInfo(settings.timezone)).date()
    recent=db.scalars(select(Post).where(Post.status.in_(['published','queued'])).order_by(Post.id.desc()).limit(20)).all()
    if sum(1 for p in recent if (p.published_at or p.created_at).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()==local_day)>=3:
        raise ValueError('Daily maximum of three posts reached')
    if post.article_id:
        others=db.scalars(select(Post).where(Post.article_id==post.article_id,Post.id!=post.id,Post.status.in_(['published','queued']))).all()
        if others: raise ValueError('Article already published or queued')
    try:
        result=publisher().publish(post.text)
        post.publisher_response=result
        post.status='published' if result['state']=='published' else 'queued'
        post.published_at=now() if post.status=='published' else None
    except Exception as exc:
        post.status='failed'; post.failure_reason=str(exc)
        db.commit()
        raise
    db.commit(); db.refresh(post)
    return post

def run_pipeline(dry_run=None, ai=None, fetch_new=True):
    # Explicit dry-run always wins. Settings are the final publish gate.
    dry=settings.dry_run if dry_run is None else dry_run
    with SessionLocal() as db:
        run=Run(); db.add(run); db.commit(); db.refresh(run)
        try:
            stories,errors=fetch_stories() if fetch_new else ([],[]); run.stories_fetched=len(stories)
            existing=db.scalars(select(Article).order_by(Article.id.desc()).limit(1000)).all()
            recent_posts=db.scalars(select(Post).where(Post.status.in_(['published','queued'])).order_by(Post.id.desc()).limit(20)).all()
            new=[]; seen=[]
            for s in stories:
                if duplicate(s,existing) or duplicate(s,seen): continue
                seen.append(type('Seen',(),{'url':s['url'],'title':s['title']})())
                score,reason=score_story(s,interests(),recent_posts)
                a=Article(title=s['title'],description=s['description'],url=s['url'],normalized_title=s['normalized_title'],source=s['source'],category=s['category'],published_at=s['published_at'],score=score,reason=reason,topic=topic_for(s))
                db.add(a); new.append(a)
            db.commit()
            # Previously seen but unposted articles remain eligible for later windows.
            source_priorities={s['name']:int(s.get('priority',1)) for s in yaml.safe_load((ROOT/'config/sources.yaml').read_text(encoding='utf-8'))['sources']}
            candidates=db.scalars(select(Article).where(Article.seen_at>=now()-timedelta(days=7),Article.skipped==False).order_by(Article.id.desc()).limit(500)).all()
            used={p.article_id for p in db.scalars(select(Post).where(Post.article_id.is_not(None))).all()}
            ranked=[]
            automation_row=db.get(WorkspaceSetting,'automation')
            threshold=(automation_row.value.get('minimum_relevance',settings.min_score) if automation_row else settings.min_score)
            for a in candidates:
                if a.id in used: continue
                published=a.published_at.replace(tzinfo=timezone.utc) if a.published_at and a.published_at.tzinfo is None else a.published_at
                s={'title':a.title,'description':a.description,'category':a.category,'published_at':published,'priority':source_priorities.get(a.source,1)}
                a.score,a.reason=score_story(s,interests(),recent_posts)
                if a.score>=threshold: ranked.append(a)
            selected=max(ranked,key=lambda a:a.score,default=None)
            if not selected:
                run.status='skipped'; run.detail='No suitable unposted story. '+ '; '.join(errors[:3]); db.commit()
                return {'run_id':run.id,'status':'skipped','reason':run.detail,'stories_fetched':run.stories_fetched}
            post=generate_for_article(db,selected,run,ai)
            if post.status=='failed': run.status='failed'; run.detail=post.failure_reason
            elif dry or settings.dry_run: run.status='dry_run'; run.detail='Validated; no publishing attempted'
            else:
                publish_post(db,post); run.status=post.status
            db.commit()
            return {'run_id':run.id,'status':run.status,'article':selected.title,'source':selected.source,'url':selected.url,'score':selected.score,'reason_selected':selected.reason,'style':post.style,'post':post.text,'validation':'PASS' if post.status!='failed' else post.failure_reason,'would_publish':post.status!='failed','post_id':post.id,'feed_errors':errors}
        except Exception as exc:
            run.status='failed';run.detail=str(exc);db.commit()
            return {'run_id':run.id,'status':'failed','reason':str(exc),'stories_fetched':run.stories_fetched}
