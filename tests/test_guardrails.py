"""Phase 7 成本與重試治理測試。"""

from __future__ import annotations

import pytest

from crazysoul.config import Config
from crazysoul.guardrails import check_budget, estimated_spend, retry_call
from crazysoul.models import CostEntry


def test_estimated_spend_applies_retry_factor():
    cfg = Config(cost_retry_factor=1.5)
    costs = [CostEntry("video", "x", 1.0), CostEntry("image", "x", 0.5)]
    assert estimated_spend(costs, cfg) == 2.25


def test_check_budget_includes_next_cost():
    cfg = Config(cost_limit_usd=1.0, cost_retry_factor=1.4)
    with pytest.raises(RuntimeError):
        check_budget(cfg, [CostEntry("video", "x", 0.6)], next_cost=0.2)


def test_retry_call_retries_until_success():
    cfg = Config(retry_max_attempts=3, retry_backoff_seconds=0)
    seen = {"count": 0}

    def flaky():
        seen["count"] += 1
        if seen["count"] < 2:
            raise ValueError("boom")
        return "ok"

    assert retry_call(flaky, cfg, label="flaky") == "ok"
    assert seen["count"] == 2
