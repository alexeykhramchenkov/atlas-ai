

from __future__ import annotations

from typing import Any

from db.client import supabase


def write_sync_event(
    event_type: str,
    event_status: str | None = None,
    user_id: int | None = None,
    shop_id: int | None = None,
    marketplace: str | None = None,
    source_name: str | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    row = {
        "event_type": event_type,
        "event_status": event_status,
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "message": message,
        "payload": payload or {},
    }

    response = (
        supabase
        .table("system_sync_events")
        .insert(row)
        .execute()
    )

    return response.data or []