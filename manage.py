import argparse
import json
from app.database import SessionLocal, Post, init_db
from app.service import run_pipeline

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('dry-run');sub.add_parser('run')
    rate=sub.add_parser('rate-post');rate.add_argument('post_id',type=int);rate.add_argument('rating',choices=['like','dislike']);rate.add_argument('reason',nargs='?')
    args=parser.parse_args();init_db()
    if args.command in {'dry-run','run'}: print(json.dumps(run_pipeline(dry_run=args.command=='dry-run'),indent=2,default=str))
    else:
        with SessionLocal() as db:
            p=db.get(Post,args.post_id)
            if not p: parser.error('post not found')
            p.feedback=args.rating;p.feedback_reason=args.reason;db.commit();print(f'Rated post {p.id}: {p.feedback}')
if __name__=='__main__': main()
