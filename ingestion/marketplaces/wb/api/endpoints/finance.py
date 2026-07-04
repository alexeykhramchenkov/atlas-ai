from __future__ import annotations
from ingestion.marketplaces.wb.api.client import WBClient, wb_client


REALIZATION_REPORT_URL = (
    "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
)


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

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url=REALIZATION_REPORT_URL,
        params={
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": limit,
            "rrdid": rrdid,
        },
    )


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
            break

        rrdid = last_rrd_id

        if len(rows) < limit:
            break

    return all_rows