from __future__ import annotations

import time
from typing import Any

import requests

from core.config import WB_API_KEY
from core.logger import logger


class WBAPIError(Exception):
    pass


class WBRateLimitError(WBAPIError):
    pass


class WBClient:
    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        retries: int = 3,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries

        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        json: dict | list | None = None,
        retries: int | None = None,
        timeout: int | None = None,
    ) -> Any:
        max_retries = retries or self.retries

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json,
                    timeout=timeout or self.timeout,
                )

                if response.status_code == 200:
                    logger.info(
                        f"WB API success | {method} | {url} | status=200"
                    )
                    return response.json()

                if response.status_code == 204:
                    logger.info(
                        f"WB API empty response | {method} | {url} | status=204"
                    )
                    return []

                if response.status_code == 429:
                    wait_time = min(60, attempt * 10)

                    logger.warning(
                        f"WB API rate limit | wait={wait_time}s | url={url}"
                    )

                    time.sleep(wait_time)
                    continue

                logger.error(
                    f"WB API error | status={response.status_code} | "
                    f"url={url} | response={response.text[:300]}"
                )

                raise WBAPIError(
                    f"WB API error {response.status_code}: {response.text}"
                )

            except requests.RequestException as exc:
                logger.warning(
                    f"WB request failed | attempt={attempt} | url={url} | error={exc}"
                )

                if attempt == max_retries:
                    raise WBAPIError(str(exc)) from exc

                time.sleep(attempt * 3)

        raise WBRateLimitError(f"Retries exceeded for {url}")

    def get(
        self,
        url: str,
        params: dict | None = None,
        retries: int | None = None,
        timeout: int | None = None,
    ) -> Any:
        return self.request(
            method="GET",
            url=url,
            params=params,
            retries=retries,
            timeout=timeout,
        )

    def post(
        self,
        url: str,
        json: dict | list | None = None,
        retries: int | None = None,
    ) -> Any:
        return self.request(
            method="POST",
            url=url,
            json=json,
            retries=retries,
        )


wb_client = WBClient(api_key=WB_API_KEY)


def get_sales(date_from: str, flag: int = 0):
    return wb_client.get(
        url="https://statistics-api.wildberries.ru/api/v1/supplier/sales",
        params={
            "dateFrom": date_from,
            "flag": flag,
        },
    )


def get_orders(date_from: str, flag: int = 0, api_token: str | None = None):
    client = WBClient(api_key=api_token) if api_token else wb_client
    return client.get(
        url="https://statistics-api.wildberries.ru/api/v1/supplier/orders",
        params={
            "dateFrom": date_from,
            "flag": flag,
        },
    )


def get_stocks(date_from: str = "2020-01-01"):
    return wb_client.get(
        url="https://statistics-api.wildberries.ru/api/v1/supplier/stocks",
        params={
            "dateFrom": date_from,
        },
    )


def get_realization_reports(date_from: str, date_to: str):
    return wb_client.get(
        url="https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod",
        params={
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": 100000,
        },
    )


def get_content_cards(limit: int = 100, offset: int = 0, api_token: str | None = None):
    client = WBClient(api_key=api_token) if api_token else wb_client
    return client.post(
        url="https://content-api.wildberries.ru/content/v2/get/cards/list",
        json={
            "settings": {
                "cursor": {
                    "limit": limit,
                    "offset": offset,
                },
                "filter": {
                    "withPhoto": -1,
                },
            }
        },
    )