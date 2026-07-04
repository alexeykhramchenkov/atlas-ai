import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from detectors.detector_types import DetectorEvent


EVENTS_TABLE = "events"


def normalize_product_entity_id(marketplace: str, entity_type: Optional[str], entity_id: Optional[str]) -> Optional[str]:
    if entity_type != "product" or entity_id is None:
        return entity_id

    value = str(entity_id)

    if marketplace == "wb" and not value.startswith("wb_"):
        return f"wb_{value}"

    return value


def build_event_key(row: dict) -> str:
    parts = [
        row.get("event_type") or "unknown_event",
        row.get("marketplace") or "unknown_marketplace",
        str(row.get("user_id")),
        str(row.get("shop_id")) if row.get("shop_id") is not None else "none",
        row.get("event_date") or "unknown_date",
        row.get("entity_type") or "none",
        row.get("entity_id") or "none",
    ]

    if row.get("sub_entity_type") and row.get("sub_entity_id"):
        parts.extend([
            row.get("sub_entity_type"),
            str(row.get("sub_entity_id")),
        ])

    return ":".join(parts)


def event_to_row(event: DetectorEvent) -> dict:
    payload = dict(event.payload or {})
    meta = dict(event.meta or {})

    entity_type = event.entity_type
    entity_id = event.entity_id
    sub_entity_type = event.sub_entity_type
    sub_entity_id = event.sub_entity_id

    if event.event_domain == "ads":
        nm_id = payload.get("nm_id") or entity_id
        ad_id = payload.get("ad_id") or sub_entity_id
        app_type = payload.get("app_type")

        entity_type = "product"
        entity_id = str(nm_id) if nm_id is not None else None
        sub_entity_type = "ad_campaign"
        sub_entity_id = str(ad_id) if ad_id is not None else None

        if nm_id is not None:
            payload["nm_id"] = nm_id
        if ad_id is not None:
            payload["ad_id"] = ad_id
        if ad_id is not None and "placement" not in payload:
            payload["placement"] = f"{ad_id}_{app_type}" if app_type is not None else str(ad_id)

    entity_id = normalize_product_entity_id(
        marketplace=event.marketplace,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    if entity_id and entity_type == "product":
        payload.setdefault("product_key", entity_id)

    row = {
        "user_id": event.user_id,
        "shop_id": event.shop_id,
        "marketplace": event.marketplace,
        "event_domain": event.event_domain,
        "event_type": event.event_type,
        "event_group": event.event_group,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "sub_entity_type": sub_entity_type,
        "sub_entity_id": str(sub_entity_id) if sub_entity_id is not None else None,
        "related_entities": event.related_entities or {},
        "severity": event.severity,
        "confidence": event.confidence,
        "priority": event.priority,

        "share_pct": event.share_pct,
        "share_metric": event.share_metric,
        "share_period_days": event.share_period_days,

        "is_alert": event.is_alert,
        "event_date": event.event_date.isoformat(),
        "digest_date": event.digest_date.isoformat() if event.digest_date else None,
        "title": getattr(event, "title", None),
        "description": getattr(event, "description", None),
        "source_table": event.source_table,
        "payload": payload,
        "meta": meta,
        "status": getattr(event, "status", "active") or "active",
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }

    row["event_key"] = build_event_key(row)
    return row


def write_events(events: List[DetectorEvent]) -> int:
    if not events:
        print("No events to write")
        return 0

    rows = [event_to_row(event) for event in events]

    response = (
        supabase
        .table(EVENTS_TABLE)
        .upsert(rows, on_conflict="event_key")
        .execute()
    )

    written = len(response.data or rows)
    print(f"Events written: {written}")
    return written