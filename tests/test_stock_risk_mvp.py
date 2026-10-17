from unittest.mock import patch
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from ai_chat.internal_tools.get_stocks import get_stocks

from test_get_stocks_contract import StockDB as DB

class StockRiskTest(unittest.TestCase):

    def test_current_stock_api_pages(self):
        from unittest.mock import patch, Mock
        from ingestion.marketplaces.wb.api.endpoints import stocks
        client=Mock()
        client.post.side_effect=[{'data':{'items':[{'nmId':1},{'nmId':2}]}},{'data':{'items':[{'nmId':3}]}}]
        with patch.object(stocks,'wb_client',client),patch.object(stocks,'PAGE_SIZE',2),patch.object(stocks.time,'sleep'):
            self.assertEqual([r['nmId'] for r in stocks.get_stocks()],[1,2,3])
        self.assertEqual([c.kwargs['json']['offset'] for c in client.post.call_args_list],[0,2])

    def test_current_stock_variant_id(self):
        from normalized.normalized_wb_stocks import build_stock_row
        r=build_stock_row({'user_id':1,'shop_id':1},{'nmId':99,'chrtId':123,'warehouseName':'Коледино','quantity':2})
        self.assertEqual(r['variant_key'],'wb_123')
        self.assertEqual(r['quantity'],2)

    def test_followup_context_isolation(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from telegram_bot import stock_followups as sf
        req={'user_id':1,'shop_id':1,'marketplace':'wb','telegram_user_id':10,'telegram_chat_id':20}
        with TemporaryDirectory() as folder,patch.object(sf,'STORE',Path(folder)):
            token=sf.save_context(req,{'rows':[{'product_key':'a'}]})
            self.assertIsNotNone(sf.load_context(token,10,20,req))
            self.assertIsNone(sf.load_context(token,11,20,req))
            self.assertIsNone(sf.load_context(token,10,21,req))
            self.assertIsNone(sf.load_context(token,10,20,{**req,'shop_id':2}))
            self.assertEqual(len(sf.keyboard(token).inline_keyboard),3)



    def test_pages_tenant_and_window(self):
        tenant={'user_id':1,'shop_id':1,'marketplace':'wb'};snapshot=str(datetime.now(ZoneInfo('Europe/Moscow')).date())
        stocks=[{**tenant,'id':x,'snapshot_date':snapshot,'product_key':f'p{x:05}','total_quantity':10,'total_in_way_to_client':0,'total_in_way_from_client':0} for x in range(2001)]
        stocks+=[{**stocks[0],'id':99999,'user_id':2,'total_quantity':999}]
        i=get_stocks(user_id=1,shop_id=1,supabase=DB({'raw_wb_stocks':[{**tenant,'id':1,'snapshot_date':snapshot}],'metrics_stocks_daily':stocks,'normalized_products':[]}))
        self.assertEqual(len(i['products']),2001);self.assertEqual(i['total_quantity'],20010)

if __name__=='__main__': unittest.main()
