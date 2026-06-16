import json
import logging
from datetime import datetime, timezone


LOGGER = logging.getLogger("copilot.audit")


def log_event(event_name: str, payload: dict | None = None) -> None:
    record = {
        "event": event_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
    LOGGER.info(json.dumps(record, sort_keys=True))
