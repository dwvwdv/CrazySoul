"""[3] Image Provider Layer。

Phase 0 主力:Flux via fal.ai。Phase 3 抽象化:所有生圖 Provider 都實作
`ImageProvider` 介面並註冊,業務邏輯用字串選 Provider(`cfg.image_provider`)。
另備第二家 `fal-sdxl` 驗證抽象成立。

count=n 採原生批量:一次 API 呼叫產生多張(dry-run 則一次產生多張佔位圖)。
角色一致性(Phase 2):seed 走平台原生一致性參數、style_tag 併入 prompt。
"""

from __future__ import annotations

from pathlib import Path

from .. import ffmpeg
from ..config import Config
from ..models import Character, CostEntry, Shot
from . import falai
from .base import (
    ImageProvider,
    ImageRequest,
    get_image_provider,
    register_image_provider,
)


class _FalImageProvider(ImageProvider):
    """fal.ai 系生圖 Provider 的共用實作,子類只需給 endpoint / 單價 / 佔位色相位移。"""

    endpoint: str = ""
    hue_shift: int = 0  # dry-run 佔位圖的色相位移,讓不同 Provider 肉眼可分辨

    def generate(
        self,
        req: ImageRequest,
        out_paths: list[Path],
        cfg: Config,
        costs: list[CostEntry],
        start: int = 0,
    ) -> list[Path]:
        count = len(out_paths)
        base_seed = req.base_seed()
        if cfg.dry_run:
            for k, out in enumerate(out_paths):
                idx = start + k
                # 佔位 seed:分鏡 × 候選 × 角色 seed × Provider 位移,盡量拉開差異
                seed = req.shot_index * 10 + idx + (base_seed or 0) + self.hue_shift
                ffmpeg.make_placeholder_image(out, label=req.prompt, seed=seed)
                costs.append(
                    CostEntry("image", f"dry-run/{self.name}", 0.0, f"分鏡{req.shot_index} 候選{idx}")
                )
            return out_paths

        if not cfg.fal_key:
            raise RuntimeError("未設定 FAL_KEY(或改用 --dry-run)。")

        payload: dict = {
            "prompt": req.effective_prompt(),
            "image_size": "portrait_16_9",
            "num_images": count,  # 原生批量
        }
        if base_seed is not None:
            payload["seed"] = base_seed  # 角色一致性:固定 seed
        result = falai.run_model(cfg.fal_key, endpoint=self.endpoint, payload=payload)
        images = result.get("images", [])
        for k, out in enumerate(out_paths):
            # 批量結果不足時退回逐張呼叫,確保每個候選都有圖
            url = images[k]["url"] if k < len(images) else self._single(req, cfg, base_seed, start + k)
            falai.download(url, out, cfg.fal_key)
            costs.append(
                CostEntry(
                    "image", self.name, self.unit_cost_usd, f"分鏡{req.shot_index} 候選{start + k}"
                )
            )
        return out_paths

    def _single(self, req: ImageRequest, cfg: Config, base_seed: int | None, idx: int) -> str:
        """批量數量不足時的補償:單張呼叫,seed 位移拉開差異。"""
        payload = {
            "prompt": req.effective_prompt(),
            "image_size": "portrait_16_9",
            "num_images": 1,
            "seed": (base_seed or 0) + idx,
        }
        return falai.run_model(cfg.fal_key, endpoint=self.endpoint, payload=payload)["images"][0]["url"]


@register_image_provider
class FluxImageProvider(_FalImageProvider):
    name = "fal-flux"
    unit_cost_usd = 0.025  # 粗估,Phase 7 定期寫回設定檔
    endpoint = "fal-ai/flux/dev"
    hue_shift = 0


@register_image_provider
class SdxlImageProvider(_FalImageProvider):
    """第二家生圖 Provider,驗證抽象成立(fal.ai Fast-SDXL)。"""

    name = "fal-sdxl"
    unit_cost_usd = 0.01
    endpoint = "fal-ai/fast-sdxl"
    hue_shift = 120  # dry-run 佔位圖色相與 flux 錯開,方便肉眼分辨走哪家


def generate_images(
    req: ImageRequest,
    out_paths: list[Path],
    cfg: Config,
    costs: list[CostEntry],
    start: int = 0,
) -> list[Path]:
    """統一入口:依 `cfg.image_provider` 選 Provider,原生批量產出多張。"""
    return get_image_provider(cfg.image_provider).generate(req, out_paths, cfg, costs, start)


def generate_image(
    shot: Shot,
    out_path: Path,
    cfg: Config,
    costs: list[CostEntry],
    variant: int = 0,
    characters: list[Character] | None = None,
) -> Path:
    """單張生圖的相容包裝(pipeline / 舊呼叫端用)。variant 用來產生不同候選。"""
    req = ImageRequest(prompt=shot.description, shot_index=shot.index, characters=characters or [])
    return generate_images(req, [out_path], cfg, costs, start=variant)[0]
