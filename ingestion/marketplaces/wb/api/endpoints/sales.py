

from __future__ import annotations

from typing import Any

from ingestion.marketplaces.wb.api.client import WBClient, wb_client


SALES_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"


def get_sales(
    date_from: str,
    flag: int = 0,
    api_token: str | None = None,
) -> list[dict[str, Any]]:
    """
    Получить продажи WB.

    WB API: GET /api/v1/supplier/sales

    Важно: этот endpoint возвращает события продаж за период от dateFrom.
    Каждая строка ответа — отдельная продажа/возвратная операция WB.
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    payload = client.get(
        url=SALES_URL,
        params={
            "dateFrom": date_from,
            "flag": flag,
        },
    )

    return payload or []