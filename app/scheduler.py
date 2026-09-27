from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from .config import settings
from .database import init_db
from .service import run_pipeline

def build_scheduler():
    zone=ZoneInfo(settings.timezone)
    scheduler=BlockingScheduler(timezone=zone)
    for time in settings.post_times.split(','):
        hour,minute=map(int,time.strip().split(':'))
        if hour not in range(24) or minute not in range(60): raise ValueError(f'invalid POST_TIMES entry: {time}')
        scheduler.add_job(run_pipeline,'cron',hour=hour,minute=minute,id=f'post_{hour:02d}{minute:02d}',max_instances=1,coalesce=True,misfire_grace_time=1800)
    return scheduler

if __name__=='__main__':
    init_db();build_scheduler().start()
