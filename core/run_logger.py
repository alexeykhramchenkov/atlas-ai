import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


DETECTOR_RUNS_TABLE = "detector_runs"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def write_detector_run(
    detector_name: str,
    status: str,
    started_at: datetime,
    finished_at: Optional[datetime] = None,
    detector_domain: Optional[str] = None,
    detector_group: Optional[str] = None,
    snapshot_date: Optional[str] = None,
    rows_checked: int = 0,
    events_created: int = 0,
    error_message: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    finished_at = finished_at or utc_now()
    duration_sec = round((finished_at - started_at).total_seconds(), 2)

    row = {
        "detector_name": detector_name,
        "detector_domain": detector_domain,
        "detector_group": detector_group,
        "status": status,
        "snapshot_date": snapshot_date,
        "rows_checked": rows_checked,
        "events_created": events_created,
        "duration_sec": duration_sec,
        "error_message": error_message,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "meta": meta or {},
    }

    supabase.table(DETECTOR_RUNS_TABLE).insert(row).execute()
