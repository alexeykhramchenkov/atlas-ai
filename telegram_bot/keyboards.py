from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.config import settings


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
