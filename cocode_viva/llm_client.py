import json
import os
from pathlib import Path
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SETTINGS_PATH = PROJECT_ROOT / "config" / "local_settings.json"


def _load_local_settings() -> dict[str, str]:
    if not LOCAL_SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(LOCAL_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _setting(name: str, default: str = "") -> str:
    local_settings = _load_local_settings()
    value = os.getenv(name)
    if value is None:
        value = local_settings.get(name, default)
    return str(value).strip()


class LLMClient:
    """Tiny OpenAI-compatible client used only when an API key is configured."""

    def __init__(self) -> None:
        self.api_key = _setting("OPENAI_API_KEY")
        self.base_url = _setting(
            "OPENAI_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        ).rstrip("/")
        self.model = _setting("OPENAI_MODEL", "qwen3.5-122b-a10b")

    @property
    def chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def chat_json(self, system: str, user: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    self.chat_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return None
