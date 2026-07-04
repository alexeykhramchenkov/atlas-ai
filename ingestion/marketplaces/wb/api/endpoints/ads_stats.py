from typing import Any, Dict, List

from ingestion.marketplaces.wb.api.client import WBClient, wb_client


WB_ADS_STATS_URL = "https://advert-api.wildberries.ru/adv/v3/fullstats"


def get_ads_fullstats(
    advert_ids: List[int],
    date_from: str,
    date_to: str,
    api_token: str | None = None,
) -> Dict[str, Any]:
    params = {
        "ids": ",".join(str(advert_id) for advert_id in advert_ids),
        "beginDate": date_from,
        "endDate": date_to,
    }

    client = WBClient(api_key=api_token) if api_token else wb_client

    payload = client.get(
        WB_ADS_STATS_URL,
        params=params,
        timeout=180,
    )

    print(f"WB ads stats loaded | ads: {len(advert_ids)}")

    return payload
