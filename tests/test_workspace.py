import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Article, Base, Post, make_engine
from app.main import app
from app import main, workspace


def test_workspace_edit_schedule_and_settings(monkeypatch, tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path / "workspace.db"}')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    monkeypatch.setattr(workspace, 'SessionLocal', sessions)
    monkeypatch.setattr(main, 'SessionLocal', sessions)
    monkeypatch.setattr(settings, 'dry_run', True)
    voice_path = tmp_path / 'voice.md'
    examples_path = tmp_path / 'examples.json'
    sources_path = tmp_path / 'sources.yaml'
    voice_path.write_text('A curious engineer who writes directly about technology.', encoding='utf-8')
    examples_path.write_text('[]', encoding='utf-8')
    sources_path.write_text('sources: []\n', encoding='utf-8')
    monkeypatch.setattr(workspace, 'VOICE_PATH', voice_path)
    monkeypatch.setattr(workspace, 'EXAMPLES_PATH', examples_path)
    monkeypatch.setattr(workspace, 'SOURCES_PATH', sources_path)

    with sessions() as db:
        article = Article(title='Repository agents improve', description='Agents can navigate codebases.',
                          url='https://example.org/story', normalized_title='repository agents improve',
                          source='Example', category='developer tools', score=91, reason='high_priority')
        db.add(article)
        db.flush()
        post = Post(article_id=article.id, text='A grounded observation. https://example.org/story',
                    style='reaction', status='generated')
        db.add(post)
        db.commit()
        article_id, post_id = article.id, post.id

    with TestClient(app) as client:
        result = client.get('/workspace')
        assert result.status_code == 200
        assert result.json()['articles'][0]['id'] == article_id
        assert result.json()['automation']['dry_run'] is True

        changed = client.patch(f'/articles/{article_id}', json={'skipped': True})
        assert changed.status_code == 200 and changed.json()['skipped'] is True
        assert client.patch(f'/posts/{post_id}', json={'text': 'Lost the link', 'style': 'reaction'}).status_code == 422
        edited = client.patch(f'/posts/{post_id}', json={
            'text': 'The engineering workflow matters here. https://example.org/story',
            'style': 'builder_perspective'})
        assert edited.status_code == 200 and edited.json()['style'] == 'builder_perspective'

        when = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        scheduled = client.post(f'/posts/{post_id}/schedule', json={'scheduled_at': when})
        assert scheduled.status_code == 200 and scheduled.json()['status'] == 'scheduled'
        assert client.post(f'/publish/{post_id}').status_code == 409
        unscheduled = client.post(f'/posts/{post_id}/unschedule')
        assert unscheduled.status_code == 200, unscheduled.text
        assert unscheduled.json().get('status') == 'generated', unscheduled.text
        assert client.post(f'/posts/{post_id}/feedback', json={'rating': 'like', 'reason': 'good_voice'}).json()['feedback'] == 'like'

        automation = client.get('/settings/automation').json()
        automation['paused'] = True
        automation.pop('dry_run')
        assert client.put('/settings/automation', json=automation).json()['paused'] is True
        assert client.put('/settings/voice', json={'description': 'A curious engineer writing clearly about technology.',
                                                   'examples': ['Good concise observation.']}).status_code == 200
        assert json.loads(examples_path.read_text(encoding='utf-8')) == [{'text': 'Good concise observation.'}]
        sources = {'sources': [{'name': 'Example Feed', 'url': 'https://example.org/rss',
                                'category': 'technology', 'priority': 4, 'enabled': True}]}
        assert client.put('/settings/sources', json=sources).status_code == 200
        assert client.get('/settings/sources').json()['sources'][0]['name'] == 'Example Feed'


def test_scheduler_respects_pause_and_dry_run(monkeypatch, tmp_path):
    from app import scheduler
    from app.database import WorkspaceSetting
    engine = make_engine(f'sqlite:///{tmp_path / "clock.db"}')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    monkeypatch.setattr(scheduler, 'SessionLocal', sessions)
    monkeypatch.setattr(settings, 'dry_run', True)
    monkeypatch.setattr(scheduler, 'run_pipeline', lambda **kwargs: (_ for _ in ()).throw(AssertionError('ran')))
    monkeypatch.setattr(scheduler, 'publish_post', lambda *args: (_ for _ in ()).throw(AssertionError('published')))
    with sessions() as db:
        db.add(WorkspaceSetting(key='automation', value={'paused': True, 'post_times': ['00:00'],
             'timezone': 'UTC', 'discover': True, 'generate': True, 'publish_without_approval': True,
             'minimum_relevance': 85}))
        db.add(Post(text='A scheduled post', style='reaction', status='scheduled',
                    scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
    scheduler.tick()
    with sessions() as db:
        assert db.query(Post).first().status == 'scheduled'
