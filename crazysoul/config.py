"""集中管理設定與憑證讀取。

比照 README 的設計:憑證走環境變數(.env),業務邏輯不綁死任何一家 Provider。
這裡只負責「讀設定」,不做任何 Provider 呼叫。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """極簡 .env 載入器,避免為了讀設定就多裝一個套件。

    只處理 `KEY=VALUE` 格式,忽略空行與 `#` 註解;不覆蓋已存在的環境變數。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Config:
    """一次 run 所需的全部設定。"""

    # Provider 選擇(業務邏輯只認這些字串,不認底層 SDK)
    llm_provider: str = "anthropic"
    image_provider: str = "fal-flux"
    video_provider: str = "fal-kling"
    tts_provider: str = "openai-tts"

    # 模型參數
    # 使用 Anthropic 最新的 Opus 4.8 產生分鏡(擇一,也可換 OpenAI)
    llm_model: str = "claude-opus-4-8"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"

    # 憑證(dry-run 模式下可為空)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    fal_key: str | None = None
    pcloud_webdav_url: str | None = None
    pcloud_username: str | None = None
    pcloud_password: str | None = None
    pcloud_remote_dir: str = "CrazySoul"

    # 成本護欄(Phase 7 完整實作,先放參數)
    cost_limit_usd: float = 0.0
    cost_retry_factor: float = 1.4
    tts_cost_usd: float = 0.0
    retry_max_attempts: int = 2
    retry_backoff_seconds: float = 0.5

    # Phase 1 Routing:動態分鏡比例上限([0,1])。
    # 1.0=所有 needs_motion 分鏡都走付費 Video Provider;
    # 0.0=全部退回 Motion Engine(FFmpeg zoompan,零成本);
    # 中間值=最多這個比例的分鏡能走動態路徑,其餘退回靜態,用來壓成本。
    dynamic_ratio: float = 1.0

    # 執行模式
    dry_run: bool = False
    output_root: Path = field(default_factory=lambda: Path("output"))

    @classmethod
    def load(cls, dotenv: str | os.PathLike[str] | None = ".env") -> "Config":
        """從環境變數(含 .env)載入設定。"""
        if dotenv is not None:
            _load_dotenv(Path(dotenv))

        def _num(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, "") or default)
            except ValueError:
                return default

        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, "") or default)
            except ValueError:
                return default

        # 動態比例夾在 [0,1],避免設定錯誤造成分流異常。
        dynamic_ratio = min(max(_num("DYNAMIC_RATIO", 1.0), 0.0), 1.0)

        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "anthropic"),
            image_provider=os.environ.get("IMAGE_PROVIDER", "fal-flux"),
            video_provider=os.environ.get("VIDEO_PROVIDER", "fal-kling"),
            tts_provider=os.environ.get("TTS_PROVIDER", "openai-tts"),
            llm_model=os.environ.get("LLM_MODEL", "claude-opus-4-8"),
            tts_model=os.environ.get("TTS_MODEL", "gpt-4o-mini-tts"),
            tts_voice=os.environ.get("TTS_VOICE", "alloy"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
            fal_key=os.environ.get("FAL_KEY") or None,
            pcloud_webdav_url=os.environ.get("PCLOUD_WEBDAV_URL") or None,
            pcloud_username=os.environ.get("PCLOUD_USERNAME") or None,
            pcloud_password=os.environ.get("PCLOUD_PASSWORD") or None,
            pcloud_remote_dir=os.environ.get("PCLOUD_REMOTE_DIR", "CrazySoul"),
            cost_limit_usd=_num("COST_LIMIT_USD", 0.0),
            cost_retry_factor=_num("COST_RETRY_FACTOR", 1.4),
            tts_cost_usd=_num("TTS_COST_USD", 0.0),
            retry_max_attempts=max(1, _int("RETRY_MAX_ATTEMPTS", 2)),
            retry_backoff_seconds=max(0.0, _num("RETRY_BACKOFF_SECONDS", 0.5)),
            dynamic_ratio=dynamic_ratio,
        )
