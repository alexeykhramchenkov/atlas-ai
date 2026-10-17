from telegram_bot.keyboards import build_marketplace_accounts_keyboard


def test_keyboard_supports_multiple_marketplaces_and_accounts():
    keyboard = build_marketplace_accounts_keyboard(
        connections=[
            {
                "id": 10,
                "shop_id": 1,
                "marketplace": "wb",
                "external_account_name": "Основной WB",
            },
            {
                "id": 11,
                "shop_id": 2,
                "marketplace": "ozon",
                "external_account_name": "Ozon Москва",
            },
        ],
        active_connection_id=11,
        telegram_user_id=100,
        telegram_chat_id=200,
    )

    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert any("Wildberries · Основной WB" in label for label in labels)
    assert any("✅ Ozon · Ozon Москва" in label for label in labels)
    assert "context:select:10" in callbacks
    assert "context:select:11" in callbacks
