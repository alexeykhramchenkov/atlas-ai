from ingestion.marketplaces.wb.api.client import WBClient, wb_client


FEEDBACKS_URL = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"



def get_feedbacks(
    is_answered: bool = False,
    take: int = 5000,
    skip: int = 0,
    api_token: str | None = None,
):
    """
    Get WB feedbacks.

    Returns raw WB API response.
    """

    client = (
        WBClient(api_key=api_token)
        if api_token
        else wb_client
    )

    params = {
        "isAnswered": str(is_answered).lower(),
        "take": take,
        "skip": skip,
    }

    return client.get(
        url=FEEDBACKS_URL,
        params=params,
    )


if __name__ == "__main__":
    data = get_feedbacks(take=1)
    print(data)
