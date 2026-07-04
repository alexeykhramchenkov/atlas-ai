from ingestion.marketplaces.wb.api.client import WBClient, wb_client


QUESTIONS_URL = "https://feedbacks-api.wildberries.ru/api/v1/questions"



def get_questions(
    is_answered: bool = False,
    take: int = 5000,
    skip: int = 0,
    api_token: str | None = None,
):
    """
    Получить вопросы покупателей.

    Содержит:
    - текст вопроса
    - nm_id
    - createdDate
    - ответ продавца
    - статус ответа

    WB API:
    GET /api/v1/questions
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url=QUESTIONS_URL,
        params={
            "isAnswered": str(is_answered).lower(),
            "take": take,
            "skip": skip,
        },
    )
