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
        self.timeout = _safe_float(_setting("OPENAI_TIMEOUT_SECONDS", "45"), 45)

    @property
    def chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max(64, min(int(max_tokens), 4096))
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
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


def _safe_float(value: str, default: float) -> float:
    try:
        number = float(value)
    except ValueError:
        return default
    return max(3, min(number, 60))
