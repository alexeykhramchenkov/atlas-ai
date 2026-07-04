from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class DetectorContext:
    user_id: int
    shop_id: Optional[int]
    marketplace: str
    date_from: date
    date_to: date


@dataclass
class DetectorEvent:
    user_id: int
    shop_id: Optional[int]
    marketplace: str

    event_domain: str
    event_type: str
    event_group: Optional[str] = None

    entity_type: Optional[str] = None
    entity_id: Optional[str] = None

    sub_entity_type: Optional[str] = None
    sub_entity_id: Optional[str] = None

    related_entities: Dict[str, Any] = field(default_factory=dict)

    severity: float = 0
    confidence: float = 0
    priority: float = 0

    share_pct: Optional[float] = None
    share_metric: Optional[str] = None
    share_period_days: Optional[int] = None

    is_alert: bool = False

    event_date: date = field(default_factory=date.today)
    digest_date: Optional[date] = None

    title: str = ""
    description: str = ""

    source_table: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    status: str = "active"

    @property
    def event_key(self) -> str:
        parts = [
            self.event_type,
            self.marketplace,
            str(self.user_id),
            str(self.shop_id) if self.shop_id is not None else "none",
            self.event_date.isoformat(),
            self.entity_type or "none",
            self.entity_id or "none",
        ]

        if self.sub_entity_type and self.sub_entity_id:
            parts.extend([
                self.sub_entity_type,
                str(self.sub_entity_id),
            ])

        return ":".join(parts)


@dataclass
class DetectorResult:
    detector_name: str
    checked_count: int = 0
    created_count: int = 0
    skipped_count: int = 0
    events: List[DetectorEvent] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)