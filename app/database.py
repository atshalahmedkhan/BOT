from datetime import datetime, timezone
from sqlalchemy import create_engine, ForeignKey, String, Text, Float, Integer, DateTime, JSON, Boolean, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from .config import settings

class Base(DeclarativeBase): pass

def now(): return datetime.now(timezone.utc)

class Article(Base):
    __tablename__ = 'articles'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default='')
    url: Mapped[str] = mapped_column(Text, unique=True)
    normalized_title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(100))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    score: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text, default='')
    topic: Mapped[str] = mapped_column(String(100), default='')
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)

class Post(Base):
    __tablename__ = 'posts'
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey('articles.id'))
    article: Mapped[Article | None] = relationship()
    text: Mapped[str] = mapped_column(Text, default='')
    style: Mapped[str] = mapped_column(String(50), default='')
    status: Mapped[str] = mapped_column(String(30), default='generated')
    failure_reason: Mapped[str] = mapped_column(Text, default='')
    factual_claims: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publisher_response: Mapped[dict | None] = mapped_column(JSON)
    feedback: Mapped[str | None] = mapped_column(String(20))
    feedback_reason: Mapped[str | None] = mapped_column(String(50))

class Run(Base):
    __tablename__ = 'runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(30), default='running')
    detail: Mapped[str] = mapped_column(Text, default='')
    stories_fetched: Mapped[int] = mapped_column(Integer, default=0)
    ai_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Float)

class WorkspaceSetting(Base):
    __tablename__ = 'workspace_settings'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

def make_engine(url=None):
    url = url or settings.database_url
    return create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})

engine = make_engine()
SessionLocal = sessionmaker(engine)

def init_db():
    Base.metadata.create_all(engine)
    # Existing SQLite databases predate the workspace fields. Keep their history.
    if engine.dialect.name == 'sqlite':
        with engine.begin() as connection:
            columns = {column['name'] for column in inspect(connection).get_columns('articles')}
            if 'skipped' not in columns:
                connection.execute(text('ALTER TABLE articles ADD COLUMN skipped BOOLEAN NOT NULL DEFAULT 0'))
            columns = {column['name'] for column in inspect(connection).get_columns('posts')}
            if 'scheduled_at' not in columns:
                connection.execute(text('ALTER TABLE posts ADD COLUMN scheduled_at DATETIME'))
