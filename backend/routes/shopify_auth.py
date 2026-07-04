from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.config import settings
from integrations.repository import (
    consume_oauth_state,
    create_oauth_state,
    save_connected_shopify_account,
)
from integrations.shopify.oauth import (
    build_authorization_url,
    exchange_code_for_access_token,
    normalize_shop_domain,
    verify_shopify_hmac,
)


router = APIRouter(prefix="/auth/shopify", tags=["shopify-auth"])


def require_shopify_config() -> None:
    missing = [
        name
        for name, value in {
            "APP_BASE_URL": settings.app_base_url,
            "SHOPIFY_CLIENT_ID": settings.shopify_client_id,
            "SHOPIFY_CLIENT_SECRET": settings.shopify_client_secret,
            "SHOPIFY_REDIRECT_URI": settings.shopify_redirect_uri,
            "TOKEN_ENCRYPTION_KEY": settings.token_encryption_key,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing env: {', '.join(missing)}")


@router.get("/start", response_model=None)
def start_shopify_auth(
    telegram_id: int,
    chat_id: int | None = None,
    shop: str | None = None,
) -> HTMLResponse | RedirectResponse:
    require_shopify_config()

    if not shop:
        chat_id_input = ""
        if chat_id is not None:
            chat_id_input = (
                f'<input type="hidden" name="chat_id" value="{escape(str(chat_id))}">'
            )

        return HTMLResponse(
            f"""
            <html>
              <body>
                <h1>Подключить Shopify</h1>
                <form method="get" action="/auth/shopify/start">
                  <input type="hidden" name="telegram_id" value="{escape(str(telegram_id))}">
                  {chat_id_input}
                  <label>Shop domain</label>
                  <input name="shop" placeholder="your-store.myshopify.com" required>
                  <button type="submit">Continue</button>
                </form>
              </body>
            </html>
            """
        )

    try:
        shop_domain = normalize_shop_domain(shop)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.oauth_state_ttl_seconds
    )
    state = create_oauth_state(
        provider="shopify",
        tg_user_id=telegram_id,
        tg_chat_id=chat_id,
        external_account_id=shop_domain,
        expires_at=expires_at,
    )

    auth_url = build_authorization_url(
        shop_domain=shop_domain,
        state=state,
        client_id=settings.shopify_client_id or "",
        redirect_uri=settings.shopify_redirect_uri or "",
        scopes=settings.shopify_scopes,
    )
    return RedirectResponse(auth_url, status_code=302)


@router.get("/callback")
async def shopify_callback(request: Request) -> HTMLResponse:
    require_shopify_config()

    params = dict(request.query_params)
    code = params.get("code")
    shop = params.get("shop")
    state = params.get("state")

    if not code or not shop or not state:
        raise HTTPException(status_code=400, detail="Missing Shopify OAuth callback params")

    try:
        shop_domain = normalize_shop_domain(shop)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if not verify_shopify_hmac(
        params=params,
        client_secret=settings.shopify_client_secret or "",
    ):
        raise HTTPException(status_code=400, detail="Invalid Shopify HMAC")

    oauth_state = consume_oauth_state(
        provider="shopify",
        state=state,
        external_account_id=shop_domain,
    )
    if not oauth_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    token_payload = await exchange_code_for_access_token(
        shop_domain=shop_domain,
        code=code,
        client_id=settings.shopify_client_id or "",
        client_secret=settings.shopify_client_secret or "",
    )
    access_token = token_payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="Shopify did not return access_token")

    connection = save_connected_shopify_account(
        tg_user_id=int(oauth_state["tg_user_id"]),
        tg_chat_id=oauth_state.get("tg_chat_id"),
        shop_domain=shop_domain,
        access_token=access_token,
        scopes=[scope.strip() for scope in settings.shopify_scopes.split(",") if scope.strip()],
        token_payload=token_payload,
    )

    await send_telegram_success_message(
        chat_id=oauth_state.get("tg_chat_id") or oauth_state["tg_user_id"],
        shop_domain=shop_domain,
    )

    telegram_url = build_telegram_return_url()
    return HTMLResponse(
        f"""
        <html>
          <body>
            <h1>Shopify успешно подключен ✅</h1>
            <p>{escape(shop_domain)} подключен к Atlas.</p>
            <p>Connection ID: {escape(str(connection.get("id", "")))}</p>
            <a href="{escape(telegram_url)}">Вернуться в Telegram</a>
          </body>
        </html>
        """
    )


def build_telegram_return_url() -> str:
    if not settings.telegram_bot_username:
        return "https://telegram.org/"

    query = urlencode({"start": "shopify_connected"})
    return f"https://t.me/{settings.telegram_bot_username}?{query}"


async def send_telegram_success_message(chat_id: int, shop_domain: str) -> None:
    if not settings.telegram_bot_token:
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"Shopify успешно подключен ✅\n{shop_domain}",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, json=payload)
        except httpx.HTTPError:
            pass
