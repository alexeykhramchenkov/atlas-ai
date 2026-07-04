

from __future__ import annotations

from typing import Any

from ingestion.marketplaces.wb.api.client import WBClient, wb_client


ORDERS_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"


def get_orders(
    date_from: str,
    flag: int = 0,
    api_token: str | None = None,
) -> list[dict[str, Any]]:
    """
    Получить заказы WB.

    WB API: GET /api/v1/supplier/orders

    Важно: endpoint возвращает события заказов начиная с dateFrom.
    Каждая строка ответа — отдельный заказ WB.
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    payload = client.get(
        url=ORDERS_URL,
        params={
            "dateFrom": date_from,
            "flag": flag,
        },
    )

    return payload or []