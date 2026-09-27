import re
from difflib import SequenceMatcher
from .news import norm_title

def x_length(s):
    # X counts URLs as 23 characters; conservative for ordinary Unicode.
    return len(re.sub(r'https?://\S+', 'x'*23, s))

def validate_post(generated, article, previous):
    text = generated.post.strip()
    errors=[]
    if not text: errors.append('empty post')
    if not article.url.startswith(('https://','http://')): errors.append('missing source URL')
    if article.url in text: errors.append('model included URL; application appends it')
    full = f'{text}\n\n{article.url}'
    if x_length(full)>280: errors.append('over 280 X characters')
    if len(re.findall(r'(?<!\w)#\w+',text))>2: errors.append('too many hashtags')
    if len(re.findall(r'[\U0001F300-\U0001FAFF]',text))>2: errors.append('too many emoji')
    if re.search(r"\b(I|we)\s+(tried|tested|used|attended|spoke|met|visited|built|saw)\b|\b(I've|we've)\s+(tried|tested|used|attended|spoken|met|visited|built|seen)\b",text,re.I): errors.append('unsupported personal experience')
    if generated.confidence < .65: errors.append('low model confidence')
    if any(p.article_id==article.id and p.status in {'published','queued','generated'} for p in previous): errors.append('article already posted or generated')
    if any(SequenceMatcher(None, norm_title(text), norm_title(p.text)).ratio()>.82 for p in previous if p.text): errors.append('similar post already exists')
    # Heuristic claim check; semantic grounding cannot be proven automatically.
    source = (article.title+' '+article.description).lower()
    if any(n not in source for n in re.findall(r'(?<!\w)\d+(?:\.\d+)?%?',text)): errors.append('number in post absent from source')
    for claim in generated.factual_claims:
        numbers = re.findall(r'(?<!\w)\d+(?:\.\d+)?%?',claim)
        if any(n not in source for n in numbers): errors.append(f'unverifiable number in claim: {claim[:80]}')
    return errors, full
