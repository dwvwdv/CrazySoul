"""Phase 7 成本與重試治理工具。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from .config import Config
from .models import CostEntry

T = TypeVar("T")


def estimated_spend(costs: list[CostEntry], cfg: Config) -> float:
    """回傳套用重試係數後的本次 run 估算成本。"""
    return round(sum(c.unit_cost_usd for c in costs) * cfg.cost_retry_factor, 4)


def check_budget(cfg: Config, costs: list[CostEntry], *, next_cost: float = 0.0) -> None:
    """呼叫外部 Provider 前檢查本次 run 是否超過預算上限。"""
    if cfg.cost_limit_usd <= 0:
        return
    projected = (sum(c.unit_cost_usd for c in costs) + max(0.0, next_cost)) * cfg.cost_retry_factor
    if projected > cfg.cost_limit_usd:
        raise RuntimeError(
            f"預估成本 ${projected:.2f}(含 ×{cfg.cost_retry_factor} 重試係數)"
            f"超過上限 ${cfg.cost_limit_usd:.2f},中止。"
        )


def retry_call(fn: Callable[[], T], cfg: Config, *, label: str) -> T:
    """用固定上限重試外部呼叫;最後一次失敗時拋回原例外。"""
    attempts = max(1, cfg.retry_max_attempts)
    delay = max(0.0, cfg.retry_backoff_seconds)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 外部 API 邊界需要統一重試
            last_exc = exc
            if attempt >= attempts:
                break
            time.sleep(delay * attempt)
    assert last_exc is not None
    raise RuntimeError(f"{label} 失敗,已重試 {attempts} 次:{last_exc}") from last_exc
