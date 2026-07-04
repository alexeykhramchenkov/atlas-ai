

from __future__ import annotations

from typing import Any

from ingestion.marketplaces.wb.api.client import WBClient, wb_client


STOCKS_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
DEFAULT_DATE_FROM = "2019-06-20"


def get_stocks(
    date_from: str = DEFAULT_DATE_FROM,
    api_token: str | None = None,
) -> list[dict[str, Any]]:
    """
    Получить текущие остатки WB.

    WB API: GET /api/v1/supplier/stocks

    Важно: этот endpoint возвращает текущее состояние остатков,
    а не исторические остатки за период.
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    payload = client.get(
        url=STOCKS_URL,
        params={
            "dateFrom": date_from,
        },
    )

    return payload or []