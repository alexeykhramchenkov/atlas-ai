from __future__ import annotations
import re
import time
from ingestion.marketplaces.wb.api.client import WBClient, wb_client


REALIZATION_REPORT_URL = (
    "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed"
)
_last_request_at = 0.0


def legacy_field_aliases(row):
    """Keep the existing ingestion/normalization contract after WB's API version change."""
    aliases = {re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower(): v for k,v in row.items()}
    renamed = {'reportId':'realizationreport_id','sku':'barcode','vendorCode':'sa_name',
        'techSize':'ts_name','sellerOperName':'supplier_oper_name','rrDate':'rr_dt',
        'retailPriceWithDisc':'retail_price_withdisc_rub','deliveryService':'delivery_rub',
        'forPay':'ppvz_for_pay','vw':'ppvz_vw','vwNds':'ppvz_vw_nds','currency':'currency_name',
        'paidStorage':'storage_fee','paidAcceptance':'acceptance'}
    aliases.update({old:row[new] for new,old in renamed.items() if new in row})
    return {**row,**aliases}


def get_realization_report(
    date_from: str,
    date_to: str,
    limit: int = 100000,
    rrdid: int = 0,
    api_token: str | None = None,
):
    """
    Получить отчёт реализации WB.

    Содержит:
    - продажи
    - возвраты
    - комиссии
    - логистику
    - штрафы
    - хранение
    - к перечислению

    WB API:
    GET /api/v5/supplier/reportDetailByPeriod
    """

    global _last_request_at
    client = WBClient(api_key=api_token) if api_token else wb_client
    delay = 61 - (time.monotonic() - _last_request_at)
    if delay > 0:time.sleep(delay)
    _last_request_at = time.monotonic()
    payload = client.post(
        url=REALIZATION_REPORT_URL,
        json={
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": limit,
            "rrdId": rrdid,
            "period": "weekly",
        },
    )
    if not payload:return []
    if not isinstance(payload,list):raise ValueError('Unexpected WB financial report format')
    return [legacy_field_aliases(row) for row in payload]


def get_realization_report_all_pages(
    date_from: str,
    date_to: str,
    limit: int = 100000,
    api_token: str | None = None,
):
    """
    Получить полный отчёт реализации WB со всеми страницами.

    WB API отдаёт reportDetailByPeriod порциями через курсор rrdid.
    Чтобы получить весь отчёт, нужно повторять запрос, передавая последний rrd_id.
    """

    all_rows = []
    rrdid = 0

    while True:
        payload = get_realization_report(
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            rrdid=rrdid,
            api_token=api_token,
        )

        if not payload:
            break

        if isinstance(payload, dict):
            rows = payload.get("data") or payload.get("rows") or []
        else:
            rows = payload

        if not rows:
            break

        all_rows.extend(rows)

        last_rrd_id = max(int(row.get("rrd_id") or row.get("rrdId") or 0) for row in rows)

        if last_rrd_id <= rrdid:
            raise ValueError('WB financial report cursor did not advance; incomplete data rejected')

        rrdid = last_rrd_id

        # WB specifies continuing until its empty/204 response, even for short pages.

    return all_rows
