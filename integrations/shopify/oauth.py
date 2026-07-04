from __future__ import annotations

import hmac
import re
from hashlib import sha256
from urllib.parse import urlencode

import httpx


SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


def normalize_shop_domain(raw_shop: str) -> str:
    shop = raw_shop.strip().lower()
    shop = shop.removeprefix("https://").removeprefix("http://").strip("/")

    if "." not in shop:
        shop = f"{shop}.myshopify.com"

    if not SHOP_DOMAIN_RE.match(shop):
        raise ValueError("Invalid Shopify shop domain")

    return shop


def build_authorization_url(
    *,
    shop_domain: str,
    state: str,
    client_id: str,
    redirect_uri: str,
    scopes: str,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "scope": scopes,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"https://{shop_domain}/admin/oauth/authorize?{query}"


def verify_shopify_hmac(*, params: dict[str, str], client_secret: str) -> bool:
    received_hmac = params.get("hmac")
    if not received_hmac:
        return False

    message = "&".join(
        f"{key}={value}"
        for key, value in sorted(params.items())
        if key not in {"hmac", "signature"}
    )
    digest = hmac.new(
        client_secret.encode("utf-8"),
        message.encode("utf-8"),
        sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, received_hmac)


async def exchange_code_for_access_token(
    *,
    shop_domain: str,
    code: str,
    client_id: str,
    client_secret: str,
) -> dict:
    url = f"https://{shop_domain}/admin/oauth/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
