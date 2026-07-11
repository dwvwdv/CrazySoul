"""Phase 7 Provider 單價設定檔測試。"""

from __future__ import annotations

from crazysoul.pricing import load_provider_prices, provider_price


def test_provider_prices_file_has_core_providers():
    prices = load_provider_prices()
    assert prices["image"]["fal-flux"] > 0
    assert prices["video"]["fal-kling"] > 0


def test_provider_price_lookup():
    assert provider_price("video", "fal-wan") == 0.20
    assert provider_price("video", "missing") is None
