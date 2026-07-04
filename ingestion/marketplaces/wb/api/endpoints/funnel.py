from __future__ import annotations

import base64
from typing import Any

import requests

from ingestion.marketplaces.wb.api.client import WBClient, wb_client


NM_REPORT_DOWNLOADS_URL = "https://seller-analytics-api.wildberries.ru/api/v2/nm-report/downloads"
SALES_FUNNEL_PRODUCTS_URL = "https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products"


def create_nm_report_download(
    report_id: str,
    date_from: str,
    date_to: str,
    nm_ids: list[int] | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """
    Создать задачу на генерацию отчёта по воронке продаж.
    WB API: POST /api/v2/nm-report/downloads
    """

    params = {
        "startDate": date_from,
        "endDate": date_to,
        "timezone": "Europe/Moscow",
        "aggregationLevel": "day",
        "skipDeletedNm": False,
    }

    if nm_ids:
        params["nmIDs"] = nm_ids

    payload = {
        "id": report_id,
        "reportType": "DETAIL_HISTORY_REPORT",
        "userReportName": "WB funnel report",
        "params": params,
    }

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.post(
        url=NM_REPORT_DOWNLOADS_URL,
        json=payload,
    )


def get_nm_report_downloads(
    report_id: str | None = None,
    api_token: str | None = None,
) -> dict[str, Any]:
    """
    Получить список отчётов и статусы генерации.
    WB API: GET /api/v2/nm-report/downloads
    """

    params = {}

    if report_id:
        params["filter[downloadIds]"] = report_id

    client = WBClient(api_key=api_token) if api_token else wb_client

    return client.get(
        url=NM_REPORT_DOWNLOADS_URL,
        params=params,
    )


def download_nm_report_file(
    report_id: str,
    api_token: str | None = None,
) -> dict[str, Any]:
    """
    Скачать готовый отчёт.
    Файл сохраняем в RAW как base64, чтобы не потерять исходник.
    """

    url = f"{NM_REPORT_DOWNLOADS_URL}/file/{report_id}"

    client = WBClient(api_key=api_token) if api_token else wb_client

    response = requests.get(
        url=url,
        headers=client.headers,
        timeout=60,
    )

    if response.status_code == 204:
        return {
            "empty_file": True,
            "status_code": 204,
        }

    if response.status_code != 200:
        return {
            "download_error": True,
            "status_code": response.status_code,
            "text": response.text[:1000],
        }

    return {
        "file_downloaded": True,
        "content_type": response.headers.get("Content-Type"),
        "content_length": len(response.content),
        "file_base64": base64.b64encode(response.content).decode("utf-8"),
    }


def get_sales_funnel_products(
    nm_ids: list[int],
    date_from: str,
    date_to: str,
    limit: int = 100,
    offset: int = 0,
    api_token: str | None = None,
) -> dict[str, Any]:
    """
    Получить воронку продаж WB по товарам.

    WB API: POST /api/analytics/v3/sales-funnel/products
    """

    client = WBClient(api_key=api_token) if api_token else wb_client

    payload = {
        "nmIds": nm_ids,
        "brandNames": [],
        "subjectIds": [],
        "tagIds": [],
        "selectedPeriod": {
            "start": date_from,
            "end": date_to,
        },
        "timezone": "Europe/Moscow",
        "orderBy": {
            "field": "openCard",
            "mode": "desc",
        },
        "limit": limit,
        "offset": offset,
    }

    return client.post(
        url=SALES_FUNNEL_PRODUCTS_URL,
        json=payload,
    )