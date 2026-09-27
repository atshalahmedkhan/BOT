from abc import ABC, abstractmethod
import httpx
from requests_oauthlib import OAuth1
import requests
from .config import settings

class Publisher(ABC):
    @abstractmethod
    def publish(self, text): ...

class BufferPublisher(Publisher):
    def publish(self, text):
        if not settings.buffer_api_key or not settings.buffer_channel_id: raise RuntimeError('BUFFER_API_KEY and BUFFER_CHANNEL_ID required')
        query = 'mutation CreatePost($input: CreatePostInput!) { createPost(input: $input) { __typename ... on PostActionSuccess { post { id text } } ... on MutationError { message } } }'
        payload={'query':query,'variables':{'input':{'text':text,'channelId':settings.buffer_channel_id,'schedulingType':'automatic','mode':'shareNow'}}}
        with httpx.Client(timeout=30) as client:
            r=client.post('https://api.buffer.com',headers={'Authorization':f'Bearer {settings.buffer_api_key}'},json=payload)
            r.raise_for_status(); data=r.json()
        if data.get('errors'): raise RuntimeError(str(data['errors']))
        result=data.get('data',{}).get('createPost') or {}
        if result.get('__typename')!='PostActionSuccess': raise RuntimeError(result.get('message','Buffer did not accept post'))
        return {'provider':'buffer','post_id':result['post']['id'],'state':'queued_or_sending','raw':result}

class DirectXPublisher(Publisher):
    def publish(self,text):
        keys=[settings.x_api_key,settings.x_api_secret,settings.x_access_token,settings.x_access_token_secret]
        if not all(keys): raise RuntimeError('X OAuth 1.0a credentials required')
        auth=OAuth1(*keys)
        r=requests.post('https://api.x.com/2/tweets',json={'text':text},auth=auth,timeout=30)
        r.raise_for_status()
        data=r.json()
        if not data.get('data',{}).get('id'): raise RuntimeError(f'X did not return post ID: {data}')
        return {'provider':'x','post_id':data['data']['id'],'state':'published','raw':data}

def publisher():
    if settings.publisher=='buffer': return BufferPublisher()
    if settings.publisher=='direct_x': return DirectXPublisher()
    raise ValueError('PUBLISHER must be buffer or direct_x')
