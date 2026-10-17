"""WB onboarding in the existing integrations layer; never log credentials."""
import base64
import json
import time
import re
import requests
from integrations.security import encrypt_token, token_fingerprint
from integrations.repository import utc_now_iso
from db.client import supabase_admin

class ConnectionError(ValueError):
    pass

def looks_like_token(text):
    return bool(re.search(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{40,}\.[A-Za-z0-9_-]{10,}",text))

def validate_token(token):
    token=token.removeprefix('Bearer ').strip()
    try:
        part=token.split('.')[1]
        claims=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
        mask=int(claims['s'])
        if int(claims['exp'])<=time.time():raise ValueError()
    except Exception:
        raise ConnectionError('Неверный формат ключа или истёк срок действия.') from None
    if not mask & (1<<30):raise ConnectionError('Нужен ключ только для чтения.')
    if any(not mask & (1<<bit) for bit in (1,2,5)):
        raise ConnectionError('Нужны права Контент, Аналитика и Статистика.')
    headers={'Authorization':token}
    urls=['https://common-api.wildberries.ru/api/v1/seller-info']+[f'https://{host}/ping' for host in ['content-api.wildberries.ru','seller-analytics-api.wildberries.ru','statistics-api.wildberries.ru']]
    seller=None
    for url in urls:
        try:
            response=requests.get(url,headers=headers,timeout=20)
            if response.status_code!=200:raise ConnectionError('WB не подтвердил доступ. Проверь ключ и права или повтори позже.')
            data=response.json()
        except ConnectionError:raise
        except Exception:raise ConnectionError('Не удалось проверить доступ WB. Повтори позже.') from None
        if seller is None:seller=data
    if not seller.get('sid') or seller['sid']!=claims.get('sid'):
        raise ConnectionError('Не удалось подтвердить владельца кабинета WB.')
    return {'sid':seller['sid'],'name':seller.get('tradeMark') or seller.get('name') or 'Магазин WB'},token

def save_account(tg_user_id,seller,token,db=None):
    db=db or supabase_admin
    encrypted=encrypt_token(token)  # Fail before any database write if encryption is unavailable.
    user=db.table('system_users').upsert({'tg_user_id':tg_user_id,'is_active':True,'updated_at':utc_now_iso()},on_conflict='tg_user_id').execute().data[0]
    existing=db.table('system_marketplace_connections').select('shop_id').eq('user_id',user['id']).eq('marketplace','wb').eq('external_account_id',seller['sid']).limit(1).execute().data
    if existing:shop_id=existing[0]['shop_id']
    else:
        shop=db.table('system_shops').upsert({'user_id':user['id'],'shop_name':f"WB · {seller['name']} · {seller['sid']}",'status':'active'},on_conflict='user_id,shop_name').execute().data[0]
        shop_id=shop['id']
    connection=db.table('system_marketplace_connections').upsert({'user_id':user['id'],'shop_id':shop_id,'marketplace':'wb','external_account_id':seller['sid'],'external_account_name':seller['name'],'api_token':encrypted,'encrypted_api_token':encrypted,'token_fingerprint':token_fingerprint(token),'status':'active','scopes':['content','analytics','statistics'],'token_type':'read_only','updated_at':utc_now_iso(),'revoked_at':None},on_conflict='user_id,marketplace,external_account_id').execute().data[0]
    db.table('system_user_context').upsert({'tg_user_id':tg_user_id,'owner_user_id':user['id'],'active_user_id':user['id'],'active_shop_id':shop_id,'active_marketplace':'wb','active_connection_id':connection['id']},on_conflict='tg_user_id').execute()
    return {'name':seller['name'],'shop_id':shop_id}
