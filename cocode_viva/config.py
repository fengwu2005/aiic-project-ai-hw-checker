import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
SESSION_DIR = DATA_DIR / "sessions"
TEMPLATE_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_EXTRACTED_FILES = 80

EXPECTED_FILES = {
    "readme": "README.md",
    "final_code": "final/image_ops.py",
    "student_report": "report/report.md",
}

LOCAL_SETTINGS_PATH = PROJECT_ROOT / "config" / "local_settings.json"


def setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        value = _local_settings().get(name, default)
    return str(value).strip()


def privacy_mode() -> str:
    mode = setting("PRIVACY_MODE", "full").lower()
    return mode if mode in {"full", "balanced", "strict", "offline"} else "full"


def _local_settings() -> dict:
    if not LOCAL_SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(LOCAL_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


for directory in (DATA_DIR, UPLOAD_DIR, SESSION_DIR):
    directory.mkdir(parents=True, exist_ok=True)
