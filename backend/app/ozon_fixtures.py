"""Synthetic FBS v4 data based on the official example; never calls Ozon."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


def mock_fbs_page(since: datetime, to: datetime, *, cursor: str = "", limit: int = 100) -> dict:
    payload = json.loads((Path(__file__).parent / "fixtures" / "fbs_v4.json").read_text(encoding="utf-8"),
                         parse_float=Decimal)
    postings = [p for p in payload["postings"]
                if since <= datetime.fromisoformat(p["in_process_at"]).astimezone(timezone.utc) <= to]
    offset = int(cursor) if cursor else 0
    return {"postings": postings[offset:offset + limit],
            "has_next": offset + limit < len(postings), "cursor": str(offset + limit)}
