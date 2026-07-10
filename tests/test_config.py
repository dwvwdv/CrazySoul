"""設定載入與 .env 解析的單元測試。"""

from __future__ import annotations

import os

from crazysoul.config import Config, _load_dotenv

_ENV_KEYS = [
    "LLM_PROVIDER", "IMAGE_PROVIDER", "VIDEO_PROVIDER", "LLM_MODEL",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FAL_KEY",
    "COST_LIMIT_USD", "COST_RETRY_FACTOR", "DYNAMIC_RATIO",
]


def _clear(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_load_defaults(monkeypatch):
    _clear(monkeypatch)
    cfg = Config.load(dotenv=None)
    assert cfg.llm_provider == "anthropic"
    assert cfg.image_provider == "fal-flux"
    assert cfg.video_provider == "fal-kling"
    assert cfg.llm_model == "claude-opus-4-8"
    assert cfg.cost_retry_factor == 1.4
    assert cfg.dry_run is False
    assert cfg.anthropic_api_key is None
    assert cfg.dynamic_ratio == 1.0


def test_dynamic_ratio_clamped(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DYNAMIC_RATIO", "1.5")  # 超出上限應夾回 1.0
    assert Config.load(dotenv=None).dynamic_ratio == 1.0
    monkeypatch.setenv("DYNAMIC_RATIO", "-0.3")  # 低於下限應夾回 0.0
    assert Config.load(dotenv=None).dynamic_ratio == 0.0
    monkeypatch.setenv("DYNAMIC_RATIO", "0.5")
    assert Config.load(dotenv=None).dynamic_ratio == 0.5


def test_load_from_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("IMAGE_PROVIDER", "custom")
    monkeypatch.setenv("COST_LIMIT_USD", "2.5")
    monkeypatch.setenv("FAL_KEY", "k")
    cfg = Config.load(dotenv=None)
    assert cfg.image_provider == "custom"
    assert cfg.cost_limit_usd == 2.5
    assert cfg.fal_key == "k"


def test_bad_numeric_falls_back(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("COST_RETRY_FACTOR", "notanumber")
    cfg = Config.load(dotenv=None)
    assert cfg.cost_retry_factor == 1.4


def test_dotenv_loader(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('FAL_KEY="abc"\n# 註解\nEMPTY=\n', encoding="utf-8")
    _load_dotenv(env)
    assert os.environ["FAL_KEY"] == "abc"


def test_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "already")
    env = tmp_path / ".env"
    env.write_text("FAL_KEY=fromfile\n", encoding="utf-8")
    _load_dotenv(env)
    assert os.environ["FAL_KEY"] == "already"
