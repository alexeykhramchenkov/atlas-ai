from typing import Optional

from ingestion.marketplaces.wb.api.client import WBClient, wb_client


def get_prices(
    limit: int = 1000,
    offset: int = 0,
    nm_id: Optional[int] = None,
    api_token: str | None = None,
):
    """
    Получить товары с ценами, скидками и WB Club.
    WB API: GET /api/v2/list/goods/filter
    """

    params = {
        "limit": limit,
        "offset": offset,
    }

    if nm_id is not None:
        params["filterNmID"] = nm_id

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url="https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter",
        params=params,
    )


def get_prices_by_nm_list(nm_list, api_token: str | None = None):
    """
    Получить цены по списку артикулов WB.
    WB API: POST /api/v2/list/goods/filter
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.post(
        url="https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter",
        json={
            "nmList": nm_list,
        },
    )


def get_size_prices(
    nm_id: int,
    limit: int = 1000,
    offset: int = 0,
    api_token: str | None = None,
):
    """
    Получить цены размеров товара.
    WB API: GET /api/v2/list/goods/size/nm
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url="https://discounts-prices-api.wildberries.ru/api/v2/list/goods/size/nm",
        params={
            "nmID": nm_id,
            "limit": limit,
            "offset": offset,
        },
    )


def get_quarantine_goods(limit: int = 1000, offset: int = 0, api_token: str | None = None):
    """
    Получить товары в карантине цен.
    WB API: GET /api/v2/quarantine/goods
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url="https://discounts-prices-api.wildberries.ru/api/v2/quarantine/goods",
        params={
            "limit": limit,
            "offset": offset,
        },
    )