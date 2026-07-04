

from ingestion.marketplaces.wb.api.client import wb_client


COMMON_API_URL = "https://common-api.wildberries.ru"



def get_commission_tariffs(locale: str = "ru"):
    """
    Получить тарифы комиссий WB.
    WB API: GET /api/v1/tariffs/commission
    """

    return wb_client.get(
        url=f"{COMMON_API_URL}/api/v1/tariffs/commission",
        params={
            "locale": locale,
        },
    )



def get_box_tariffs(date: str):
    """
    Получить тарифы логистики и хранения для коробов.
    WB API: GET /api/v1/tariffs/box
    """

    return wb_client.get(
        url=f"{COMMON_API_URL}/api/v1/tariffs/box",
        params={
            "date": date,
        },
    )



def get_pallet_tariffs(date: str):
    """
    Получить тарифы логистики и хранения для паллет.
    WB API: GET /api/v1/tariffs/pallet
    """

    return wb_client.get(
        url=f"{COMMON_API_URL}/api/v1/tariffs/pallet",
        params={
            "date": date,
        },
    )



def get_return_tariffs(date: str):
    """
    Получить тарифы возвратов.
    WB API: GET /api/v1/tariffs/return
    """

    return wb_client.get(
        url=f"{COMMON_API_URL}/api/v1/tariffs/return",
        params={
            "date": date,
        },
    )