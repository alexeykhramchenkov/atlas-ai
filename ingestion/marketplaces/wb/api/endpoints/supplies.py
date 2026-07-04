from ingestion.marketplaces.wb.api.client import wb_client


SUPPLIES_API_URL = "https://supplies-api.wildberries.ru"


def get_supplies(limit: int = 1000, offset: int = 0, dates=None, status_ids=None):
    """
    Получить список FBW поставок.
    WB API: POST /api/v1/supplies
    """

    payload = {
        "dates": dates or [],
        "statusIDs": status_ids or [],
    }

    return wb_client.post(
        url=f"{SUPPLIES_API_URL}/api/v1/supplies",
        json=payload,
    )


def get_supply_details(supply_id, is_preorder_id: bool = False):
    """
    Получить детали поставки.
    WB API: GET /api/v1/supplies/{ID}
    """

    return wb_client.get(
        url=f"{SUPPLIES_API_URL}/api/v1/supplies/{supply_id}",
        params={
            "isPreorderID": str(is_preorder_id).lower(),
        },
    )


def get_supply_goods(supply_id, limit: int = 1000, offset: int = 0, is_preorder_id: bool = False):
    """
    Получить товары поставки.
    WB API: GET /api/v1/supplies/{ID}/goods
    """

    return wb_client.get(
        url=f"{SUPPLIES_API_URL}/api/v1/supplies/{supply_id}/goods",
        params={
            "limit": limit,
            "offset": offset,
            "isPreorderID": str(is_preorder_id).lower(),
        },
    )


def get_supply_package(supply_id):
    """
    Получить упаковку поставки.
    WB API: GET /api/v1/supplies/{ID}/package
    """

    return wb_client.get(
        url=f"{SUPPLIES_API_URL}/api/v1/supplies/{supply_id}/package"
    )