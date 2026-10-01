from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import base64
import json

from rasmai.config import DEBUG_EXPORT_DIR

DEBUG_EXPORTS_KEPT = 40


def instant(text: Any) -> float:
    """When a stored timestamp happened, as seconds since the epoch, whatever offset it was written with.

    Plays carry the arcade's own offset (+09:00) and the bot stamps its reads in the machine's, so
    comparing the strings compares clock faces in different time zones. A stamp with no offset is
    this machine's local time, which is how the bot writes them. One that cannot be read is 0.

    :param text: An ISO 8601 moment.
    :type text: Any
    :rtype: float
    """
    try:
        return datetime.fromisoformat(str(text)).timestamp()
    except ValueError:
        return 0.0


def _json_safe(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("utf-8")
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def export_debug_payload(payload: Dict[str, Any], export_dir: Path = DEBUG_EXPORT_DIR) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    file_path = export_dir / f"maimai-export-{timestamp}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(payload), f, indent=2, ensure_ascii=False)
    # every analysis and link with the export switched on writes one, and nothing else clears them;
    # the timestamp in the name sorts oldest first, so everything before the last forty goes
    for old in sorted(export_dir.glob("maimai-export-*.json"))[:-DEBUG_EXPORTS_KEPT]:
        old.unlink(missing_ok=True)
    return file_path
