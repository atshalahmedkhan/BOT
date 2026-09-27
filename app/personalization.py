import json
import re
import yaml
from .config import ROOT

def voice(): return (ROOT/'VOICE_PROFILE.md').read_text(encoding='utf-8')
def interests(): return yaml.safe_load((ROOT/'config/interests.yaml').read_text(encoding='utf-8'))
def examples():
    data = json.loads((ROOT/'data/style_examples.json').read_text(encoding='utf-8'))
    return [x['text'] for x in data if isinstance(x,dict) and isinstance(x.get('text'),str) and x['text'].strip()]
def select_examples(story, limit=3):
    words = set(re.findall(r'[a-z]{4,}', (story.get('title','')+' '+story.get('category','')).lower()))
    return sorted(examples(), key=lambda e: len(words & set(re.findall(r'[a-z]{4,}', e.lower()))), reverse=True)[:limit]
def feedback_signals(posts):
    return [{'rating':p.feedback, 'reason':p.feedback_reason, 'style':p.style, 'category':p.article.category if p.article else None} for p in posts if p.feedback][-10:]
