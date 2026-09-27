from datetime import datetime, timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.ai import Generated
from app.main import app
from app.news import parse_feed, norm_url, duplicate, score_story
from app.personalization import voice, examples, interests
from app.validation import validate_post
from app.scheduler import build_scheduler
from app.database import Article, Post, Base, make_engine
from app.config import settings
from app.service import publish_post
from app.service import run_pipeline

def test_feed_and_normalization():
    feed=b'<rss><channel><item><title>New AI model</title><link>https://example.com/a?utm_source=x</link><description>Test</description></item></channel></rss>'
    row=parse_feed(feed,{'name':'Example','category':'artificial intelligence','priority':2})[0]
    assert row['title']=='New AI model' and row['url']=='https://example.com/a'
    assert norm_url('https://www.EXAMPLE.com/a/?fbclid=1')=='https://example.com/a'

def test_dedupe_and_ranking():
    s={'title':'New developer agent launches','description':'Coding tool','url':'https://example.com/a','category':'developer tools','priority':4,'published_at':datetime.now(timezone.utc)}
    assert duplicate(s,[SimpleNamespace(title='New developer agent launches!',url='https://elsewhere.com/b')])
    score,reason=score_story(s,interests(),[])
    assert score>40 and 'high_priority' in reason
    a=SimpleNamespace(topic='agent',category='developer tools')
    assert score_story(s,interests(),[SimpleNamespace(article=a)])[0]<score

def test_personalization_and_output():
    assert 'Never claim personal' in voice()
    assert examples()
    g=Generated.model_validate({'post':'Interesting direction for coding tools.','style':'reaction','confidence':.9,'factual_claims':[]})
    a=SimpleNamespace(id=1,title='Coding tool announced',description='A new coding tool.',url='https://example.com/a')
    assert validate_post(g,a,[])[0]==[]
    bad=Generated(post='I tested this and it improved speed by 90%.',style='reaction',confidence=.9,factual_claims=['Improved by 90%'])
    assert validate_post(bad,a,[])[0]

def test_database_scheduler_and_api():
    engine=make_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    assert 'articles' in Base.metadata.tables
    assert len(build_scheduler().get_jobs())==len(settings.post_times.split(','))
    with TestClient(app) as client:
        assert client.get('/health').json()['dry_run'] is True
        assert client.get('/stats').status_code==200

def test_dry_run_blocks_publisher(monkeypatch):
    monkeypatch.setattr(settings,'dry_run',True)
    class Never:
        def publish(self,text): raise AssertionError('external publish invoked')
    monkeypatch.setattr('app.service.publisher',lambda:Never())
    try: publish_post(None,Post(text='test',status='generated'))
    except RuntimeError as e: assert 'DRY_RUN' in str(e)
    else: assert False

def test_mock_publisher_records_result(monkeypatch, tmp_path):
    from sqlalchemy.orm import sessionmaker
    engine=make_engine(f'sqlite:///{tmp_path / "publish.db"}');Base.metadata.create_all(engine)
    session=sessionmaker(engine)
    monkeypatch.setattr(settings,'dry_run',False)
    class FakePublisher:
        def publish(self,text): return {'provider':'fake','post_id':'123','state':'published'}
    monkeypatch.setattr('app.service.publisher',lambda:FakePublisher())
    with session() as db:
        p=Post(text='A safe custom post.',status='generated');db.add(p);db.commit()
        result=publish_post(db,p)
        assert result.status=='published' and result.publisher_response['post_id']=='123'

def test_pipeline_with_mock_ai_never_publishes(monkeypatch, tmp_path):
    from app import service
    from sqlalchemy.orm import sessionmaker
    engine=make_engine(f'sqlite:///{tmp_path / "test.db"}')
    Base.metadata.create_all(engine)
    session_factory=sessionmaker(engine)
    monkeypatch.setattr(service,'SessionLocal',session_factory)
    monkeypatch.setattr(service,'fetch_stories',lambda:([{'title':'A new coding agent handles repository tasks','description':'The coding agent can work through repository tasks.','url':'https://example.org/new-agent-test','normalized_title':'a new coding agent handles repository tasks','source':'Test Feed','category':'developer tools','priority':5,'published_at':datetime.now(timezone.utc)}],[]))
    class FakeAI:
        def generate(self,story,feedback):
            return Generated(post='The interesting part is how much of a repository task an agent can carry. That changes the shape of a small engineering team.',style='builder_perspective',confidence=.9,factual_claims=[]),100,40
    def never(): raise AssertionError('publisher invoked')
    monkeypatch.setattr(service,'publisher',never)
    result=run_pipeline(dry_run=True,ai=FakeAI())
    assert result['status']=='dry_run' and result['validation']=='PASS'
    assert result['post'].endswith('https://example.org/new-agent-test')
    with session_factory() as db:
        p=db.get(Post,result['post_id']);p.feedback='like';p.feedback_reason='good_voice';db.commit();db.refresh(p)
        assert p.feedback_reason=='good_voice'
