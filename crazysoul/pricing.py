"""Provider 單價設定檔讀取工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PRICE_FILE = Path("config/provider_prices.json")


def load_provider_prices(path: Path = DEFAULT_PRICE_FILE) -> dict[str, Any]:
    """讀取 Provider 實際/估算單價設定檔。"""
    if not path.exists():
        return {"image": {}, "video": {}, "tts": {}, "updated_at": "missing"}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "image": dict(data.get("image", {})),
        "video": dict(data.get("video", {})),
        "tts": dict(data.get("tts", {})),
        "updated_at": data.get("updated_at", "unknown"),
    }


def provider_price(stage: str, provider: str, path: Path = DEFAULT_PRICE_FILE) -> float | None:
    """回傳某 stage/provider 的單價;不存在時回 None。"""
    prices = load_provider_prices(path)
    value = prices.get(stage, {}).get(provider)
    return float(value) if value is not None else None
