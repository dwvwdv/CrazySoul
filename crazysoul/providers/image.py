"""[3] Image Provider Layer — Phase 0 主力:Flux via fal.ai。

介面:generate_image(shot, out_path, cfg, costs) → 產出一張圖。
Phase 0 一個分鏡先只生一張(count=1);批量 count=n 留到 Phase 3。
"""

from __future__ import annotations

from pathlib import Path

from .. import ffmpeg
from ..config import Config
from ..models import CostEntry, Shot
from . import falai

# Flux (fal.ai) 粗估單價,實際以帳單為準;Phase 7 會定期寫回設定檔。
_FLUX_UNIT_USD = 0.025


def generate_image(shot: Shot, out_path: Path, cfg: Config, costs: list[CostEntry]) -> Path:
    if cfg.dry_run:
        ffmpeg.make_placeholder_image(out_path, label=shot.description, seed=shot.index)
        costs.append(CostEntry("image", "dry-run", 0.0, f"分鏡{shot.index}"))
        return out_path

    if cfg.image_provider != "fal-flux":
        raise NotImplementedError(
            f"目前只實作 fal-flux 生圖 Provider(收到 {cfg.image_provider!r})。"
        )
    if not cfg.fal_key:
        raise RuntimeError("未設定 FAL_KEY(或改用 --dry-run)。")

    result = falai.run_model(
        cfg.fal_key,
        endpoint="fal-ai/flux/dev",
        payload={
            "prompt": shot.description,
            "image_size": "portrait_16_9",
            "num_images": 1,
        },
    )
    url = result["images"][0]["url"]
    falai.download(url, out_path, cfg.fal_key)
    costs.append(
        CostEntry("image", "fal-flux", _FLUX_UNIT_USD, f"分鏡{shot.index}")
    )
    return out_path
