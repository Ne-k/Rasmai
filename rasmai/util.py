from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import base64
import json

from rasmai.config import DEBUG_EXPORT_DIR


def _json_safe(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
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
    return file_path
