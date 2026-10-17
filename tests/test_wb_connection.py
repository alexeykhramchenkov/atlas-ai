import unittest,base64,json,time
from unittest.mock import patch,AsyncMock,MagicMock
from types import SimpleNamespace
from cryptography.fernet import Fernet
from integrations.security import encrypt_token,decrypt_token
from integrations.wb import validate_token,ConnectionError,save_account
from telegram_bot.wb_connection import intercept

def token(sid='seller-a',mask=(1<<30)|(1<<1)|(1<<2)|(1<<5)):
 payload=base64.urlsafe_b64encode(json.dumps({'s':mask,'exp':time.time()+3600,'sid':sid}).encode()).decode().rstrip('=')
 return 'eyJhbGciOiJIUzI1NiJ9.'+payload+'.signature-for-unit-tests'
class FakeDB:
 def __init__(self):self.tables={};self.query=None
 def table(self,name):return Query(self,name)
class Query:
 def __init__(self,db,name):self.db=db;self.name=name;self.filters=[];self.row=None
 def select(self,*a):return self
 def eq(self,k,v):self.filters.append((k,v));return self
 def limit(self,*a):return self
 def single(self):self.one=True;return self
 def upsert(self,row,on_conflict=None):self.row=row;self.keys=(on_conflict or 'id').split(',');return self
 def execute(self):
  rows=self.db.tables.setdefault(self.name,[])
  if self.row is not None:
   hit=next((x for x in rows if all(x.get(k)==self.row.get(k) for k in self.keys)),None)
   if hit is None:hit={'id':len(rows)+1};rows.append(hit)
   hit.update(self.row);return SimpleNamespace(data=[dict(hit)])
  result=[dict(x) for x in rows if all(x.get(k)==v for k,v in self.filters)]
  return SimpleNamespace(data=(result[0] if result else None) if getattr(self,"one",False) else result)
class SecurityTests(unittest.TestCase):
 def test_cipher_and_wrong_key(self):
  value=token();cipher=encrypt_token(value);self.assertNotIn(value,cipher);self.assertEqual(decrypt_token(cipher),value)
  with patch('integrations.security.settings',SimpleNamespace(token_encryption_key=Fernet.generate_key().decode())):
   with self.assertRaises(RuntimeError):decrypt_token(cipher)
 def test_two_sellers_two_owners_reconnect(self):
  db=FakeDB();a=save_account(111,{'sid':'a','name':'Same name'},token('a'),db);b=save_account(111,{'sid':'b','name':'Same name'},token('b'),db);c=save_account(222,{'sid':'a','name':'Same name'},token('a'),db)
  self.assertNotEqual(a['shop_id'],b['shop_id']);self.assertNotEqual(a['shop_id'],c['shop_id'])
  again=save_account(111,{'sid':'a','name':'New label'},token('a'),db);self.assertEqual(a['shop_id'],again['shop_id'])
  for x in db.tables['system_marketplace_connections']:
   decoded=decrypt_token(x['encrypted_api_token']).split('.')[1]
   self.assertEqual(json.loads(base64.urlsafe_b64decode(decoded+'='*(-len(decoded)%4)))['sid'],x['external_account_id'])
   # Ciphertext may coincidentally contain any short base64 substring.
   self.assertEqual(x['api_token'],x['encrypted_api_token'])
   self.assertNotEqual(x['api_token'],decrypt_token(x['encrypted_api_token']))
   self.assertTrue(x['api_token'].startswith('gAAAA'))
  self.assertNotIn('system_ai_questions',db.tables)
 def test_missing_encryption_before_any_write(self):
  db=FakeDB()
  with patch('integrations.security.settings',SimpleNamespace(token_encryption_key=None)):
   with self.assertRaises(RuntimeError):save_account(111,{'sid':'a','name':'A'},token(),db)
  self.assertEqual(db.tables,{})
 def test_api_owner_mismatch(self):
  response=MagicMock(status_code=200);response.json.return_value={'sid':'other','name':'B'}
  with patch('integrations.wb.requests.get',return_value=response):
   with self.assertRaises(ConnectionError):validate_token(token())
 def test_write_capable_token_rejected_without_api(self):
  with patch('integrations.wb.requests.get') as http:
   with self.assertRaises(ConnectionError):validate_token(token(mask=38))
   http.assert_not_called()
 def test_api_failure_message_contains_no_secret(self):
  value=token()
  with patch('integrations.wb.requests.get',side_effect=RuntimeError(value)):
   with self.assertRaises(ConnectionError) as e:validate_token(value)
  self.assertNotIn(value,str(e.exception))
class MessageTests(unittest.IsolatedAsyncioTestCase):
 def update(self,text):
  msg=SimpleNamespace(text=text,delete=AsyncMock(),reply_text=AsyncMock())
  return SimpleNamespace(message=msg,effective_chat=SimpleNamespace(type='private',id=1),effective_user=SimpleNamespace(id=111))
 async def test_success_intercept_never_echoes_secret(self):
  value=token();u=self.update(value);c=SimpleNamespace(user_data={'wb_connect':{'chat_id':1,'expires':time.time()+100}})
  with patch('telegram_bot.wb_connection.validate_token',return_value=({'sid':'a','name':'A'},value)),patch('telegram_bot.wb_connection.save_account',return_value={'name':'A','shop_id':1}):
   self.assertTrue(await intercept(u,c))
  u.message.delete.assert_awaited_once();self.assertNotIn(value,str(u.message.reply_text.call_args_list));self.assertEqual(c.user_data,{})
 async def test_unsolicited_key_does_not_reach_analytics(self):
  u=self.update(token());self.assertTrue(await intercept(u,SimpleNamespace(user_data={})));u.message.delete.assert_awaited_once()
 async def test_ordinary_question_passes(self):
  self.assertFalse(await intercept(self.update('Какие товары заканчиваются?'),SimpleNamespace(user_data={})))
 async def test_expired_state_does_not_validate_or_store(self):
  u=self.update(token());c=SimpleNamespace(user_data={'wb_connect':{'chat_id':1,'expires':0}})
  with patch('telegram_bot.wb_connection.validate_token') as validate:self.assertTrue(await intercept(u,c));validate.assert_not_called()

class LoaderTests(unittest.TestCase):
 def test_credentials_are_bound_to_user_and_shop(self):
  from ingestion.orchestrators.sync_worker import get_active_connection
  db=FakeDB();a=token('a');b=token('b')
  db.tables['system_active_sync_connections']=[{'connection_id':1,'user_id':1,'shop_id':10,'marketplace':'wb','user_is_active':True,'connection_status':'active'},{'connection_id':2,'user_id':2,'shop_id':20,'marketplace':'wb','user_is_active':True,'connection_status':'active'}]
  db.tables['system_marketplace_connections']=[{'id':1,'user_id':1,'shop_id':10,'marketplace':'wb','encrypted_api_token':encrypt_token(a)},{'id':2,'user_id':2,'shop_id':20,'marketplace':'wb','encrypted_api_token':encrypt_token(b)}]
  with patch('ingestion.orchestrators.sync_worker.supabase',db):
   self.assertEqual(get_active_connection(1,10,'wb')['api_token'],a)
   self.assertEqual(get_active_connection(2,20,'wb')['api_token'],b)
   self.assertIsNone(get_active_connection(1,20,'wb'))
 def test_missing_credential_stops_loading(self):
  from ingestion.orchestrators.sync_worker import get_active_connection
  db=FakeDB();db.tables['system_active_sync_connections']=[{'connection_id':1,'user_id':1,'shop_id':10,'marketplace':'wb','user_is_active':True,'connection_status':'active'}];db.tables['system_marketplace_connections']=[{'id':1,'user_id':1,'shop_id':10,'marketplace':'wb','encrypted_api_token':None}]
  with patch('ingestion.orchestrators.sync_worker.supabase',db):
   with self.assertRaises(RuntimeError):get_active_connection(1,10,'wb')
