from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.config import settings


MARKETPLACE_LABELS = {
    "wb": "Wildberries",
    "ozon": "Ozon",
    "yandex_market": "Яндекс Маркет",
    "shopify": "Shopify",
}


def build_marketplace_accounts_keyboard(
    *,
    connections: list[dict],
    active_connection_id: int | None,
    telegram_user_id: int | None,
    telegram_chat_id: int | None,
) -> InlineKeyboardMarkup:
    rows = []
    for connection in connections:
        marketplace = connection.get("marketplace") or "marketplace"
        account_name = (
            connection.get("external_account_name")
            or connection.get("external_account_id")
            or f"Магазин {connection.get('shop_id')}"
        )
        marker = "✅" if connection.get("id") == active_connection_id else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {MARKETPLACE_LABELS.get(marketplace, marketplace)} · {account_name}",
                    callback_data=f"context:select:{connection['id']}",
                )
            ]
        )

    shopify_connected = any(row.get("marketplace") == "shopify" for row in connections)
    if not shopify_connected:
        rows.extend(
            build_shopify_connection_keyboard(
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                shopify_connected=False,
            ).inline_keyboard
        )

    rows.append(
        [
            InlineKeyboardButton("Подключить Wildberries", callback_data="connection:planned:wb"),
            InlineKeyboardButton("Подключить Ozon", callback_data="connection:planned:ozon"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "Подключить Яндекс Маркет",
                callback_data="connection:planned:yandex_market",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_shopify_connection_keyboard(
    *,
    telegram_user_id: int | None,
    telegram_chat_id: int | None,
    shopify_connected: bool,
) -> InlineKeyboardMarkup:
    rows = []

    if shopify_connected:
        rows.append(
            [
                InlineKeyboardButton(
                    "✅ Shopify подключен",
                    callback_data="connection:shopify_connected",
                )
            ]
        )
    elif settings.app_base_url and telegram_user_id:
        query = {
            "telegram_id": str(telegram_user_id),
        }
        if telegram_chat_id is not None:
            query["chat_id"] = str(telegram_chat_id)

        shopify_url = (
            f"{settings.app_base_url.rstrip('/')}/auth/shopify/start?"
            f"{urlencode(query)}"
        )
        rows.append([InlineKeyboardButton("Подключить Shopify", url=shopify_url)])
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    "Подключить Shopify",
                    callback_data="integration_config_missing",
                )
            ]
        )

    return InlineKeyboardMarkup(rows)
