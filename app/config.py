from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    app_env: str = 'development'
    database_url: str = 'sqlite:///newsbot.db'
    timezone: str = 'America/New_York'
    post_times: str = '09:00,14:00,20:00'
    dry_run: bool = True
    ai_provider: str = 'gemini'
    ai_model: str = 'gemini-2.5-flash-lite'
    gemini_api_key: str = ''
    xai_api_key: str = ''
    openai_api_key: str = ''
    publisher: str = 'buffer'
    buffer_api_key: str = ''
    buffer_channel_id: str = ''
    x_api_key: str = ''
    x_api_secret: str = ''
    x_access_token: str = ''
    x_access_token_secret: str = ''
    min_score: float = 40
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None

settings = Settings()
