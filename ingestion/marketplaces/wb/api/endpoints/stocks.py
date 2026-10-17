"""Current WB warehouse inventory (Analytics token category)."""
from __future__ import annotations
import time
from typing import Any
from ingestion.marketplaces.wb.api.client import WBClient, wb_client

STOCKS_URL = 'https://seller-analytics-api.wildberries.ru/api/analytics/v1/stocks-report/wb-warehouses'
PAGE_SIZE = 250000


def get_stocks(date_from: str = '2019-06-20', api_token: str | None = None) -> list[dict[str, Any]]:
    client = WBClient(api_key=api_token) if api_token else wb_client
    result = []
    offset = 0
    while True:
        payload = client.post(url=STOCKS_URL, json={'limit': PAGE_SIZE, 'offset': offset})
        if not isinstance(payload, dict) or not isinstance(payload.get('data', {}).get('items'), list):
            raise ValueError('Unexpected current WB stock response')
        batch = payload['data']['items']
        result.extend(batch)
        if len(batch) < PAGE_SIZE:
            return result
        offset += len(batch)
        time.sleep(20)
