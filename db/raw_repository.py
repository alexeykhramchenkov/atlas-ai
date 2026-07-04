from datetime import datetime, timezone
from typing import Optional
from db.client import supabase


def save_raw_payload(
    table_name: str,
    user_id: int,
    payload,
    extra_fields: Optional[dict] = None,
):
    """
    Сохраняет сырой ответ WB API в RAW таблицу.
    Ничего не считает и не нормализует.

    Важно:
    - RAW таблицы проекта сейчас используют user_id, payload, loaded_at
    - дополнительные поля передаются через extra_fields
      например: advert_id, nm_id, stat_date, report_id, tariff_type
    """

    if payload is None:
        payload = {
            "raw_payload_empty": True,
            "message": "WB API returned empty/null payload",
        }

    row = {
        "user_id": user_id,
        "payload": payload,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }

    if extra_fields:
        row.update(extra_fields)

    return supabase.table(table_name).insert(row).execute()