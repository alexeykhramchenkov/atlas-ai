from ingestion.marketplaces.wb.api.client import WBClient, wb_client


def get_adverts(api_token: str | None = None):
    """
    Получить список рекламных кампаний WB
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url="https://advert-api.wildberries.ru/adv/v1/promotion/count"
    )



def get_advert_stats(advert_ids, date_from, date_to, api_token: str | None = None):
    """
    Получить статистику рекламных кампаний WB.
    WB API: GET /adv/v3/fullstats
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url="https://advert-api.wildberries.ru/adv/v3/fullstats",
        params={
            "ids": ",".join(str(advert_id) for advert_id in advert_ids),
            "beginDate": date_from,
            "endDate": date_to,
        },
    )