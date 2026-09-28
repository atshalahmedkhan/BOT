"""One minute workspace clock; reads editable automation settings each tick."""
from datetime import timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select
from .config import settings
from .database import Post, WorkspaceSetting, SessionLocal, init_db, now
from .service import publish_post, run_pipeline
from .workspace import automation, discover

def tick():
    with SessionLocal() as db:
        heartbeat=db.get(WorkspaceSetting,'scheduler_heartbeat')
        if not heartbeat: heartbeat=WorkspaceSetting(key='scheduler_heartbeat',value={});db.add(heartbeat)
        heartbeat.value={'at':now().isoformat()};db.commit()
        config=automation(db)
        if config['paused']: return
        # Scheduling a draft is explicit approval for that post.
        if not settings.dry_run:
            due=db.scalars(select(Post).where(Post.status=='scheduled',Post.scheduled_at<=now()).order_by(Post.scheduled_at).limit(3)).all()
            for post in due:
                try: publish_post(db,post)
                except Exception: pass  # publish_post stores the failure
        local=now().astimezone(ZoneInfo(config['timezone']))
        window=local.strftime('%H:%M')
        if window not in config['post_times']: return
        key=f"{local.date().isoformat()}:{window}"
        last=db.get(WorkspaceSetting,'last_window')
        if last and last.value.get('key')==key: return
        if not last: last=WorkspaceSetting(key='last_window',value={});db.add(last)
        last.value={'key':key};db.commit()
    if config['generate']:
        run_pipeline(dry_run=not config['publish_without_approval'], fetch_new=config['discover'])
    elif config['discover']:
        discover()

def build_scheduler():
    scheduler=BlockingScheduler(timezone=timezone.utc)
    scheduler.add_job(tick,'interval',minutes=1,id='workspace_clock',max_instances=1,coalesce=True,misfire_grace_time=60)
    return scheduler

if __name__=='__main__':
    init_db();build_scheduler().start()
