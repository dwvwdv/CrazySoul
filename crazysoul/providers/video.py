"""[5a] Video Provider Layer。

Phase 0 主力:Kling via fal.ai(image-to-video)。Phase 3 抽象化:所有生影片
Provider 都實作 `VideoProvider` 介面並註冊,業務邏輯用字串選(`cfg.video_provider`)。
另備第二家 `fal-wan` 驗證抽象成立。

dry-run 一律用 FFmpeg Motion Engine(zoompan)代替,零成本驗證資料流;
每個候選用不同 variant 產生不同運鏡。
"""

from __future__ import annotations

from pathlib import Path

from .. import ffmpeg
from ..config import Config
from ..models import CostEntry, Shot
from . import falai
from .base import (
    VideoProvider,
    VideoRequest,
    get_video_provider,
    register_video_provider,
)
from ..guardrails import check_budget, retry_call


class _FalVideoProvider(VideoProvider):
    """fal.ai 系 image-to-video Provider 的共用實作。"""

    endpoint: str = ""

    def generate(
        self,
        req: VideoRequest,
        out_paths: list[Path],
        cfg: Config,
        costs: list[CostEntry],
        start: int = 0,
    ) -> list[Path]:
        for k, out in enumerate(out_paths):
            variant = start + k
            if cfg.dry_run:
                ffmpeg.image_to_motion_clip(req.image_path, out, req.duration, variant=variant)
                costs.append(
                    CostEntry("video", f"dry-run/{self.name}", 0.0, f"分鏡{req.shot_index} 候選{variant}")
                )
                continue

            check_budget(cfg, costs, next_cost=self.unit_cost_usd)
            if not cfg.fal_key:
                raise RuntimeError("未設定 FAL_KEY(或改用 --dry-run)。")
            # fal.ai 需要可存取的圖片 URL;先上傳到 fal 儲存再餵給 image-to-video。
            image_url = _upload_image(req.image_path, cfg.fal_key)
            result = retry_call(
                lambda: falai.run_model(
                    cfg.fal_key,
                    endpoint=self.endpoint,
                    payload={
                        "prompt": req.motion_hint or "",
                        "image_url": image_url,
                        "duration": str(int(round(req.duration))),
                    },
                ),
                cfg,
                label=f"{self.name} video generate",
            )
            raw = out.with_name(out.stem + "_raw.mp4")
            falai.download(result["video"]["url"], raw, cfg.fal_key)
            ffmpeg.normalize_clip(raw, out, duration=req.duration)  # 統一畫布/編碼,無縫串接
            raw.unlink(missing_ok=True)
            costs.append(
                CostEntry("video", self.name, self.unit_cost_usd, f"分鏡{req.shot_index} 候選{variant}")
            )
        return out_paths


@register_video_provider
class KlingVideoProvider(_FalVideoProvider):
    name = "fal-kling"
    unit_cost_usd = 0.28  # 每段約 5 秒,粗估,實際以帳單為準
    endpoint = "fal-ai/kling-video/v1/standard/image-to-video"


@register_video_provider
class WanVideoProvider(_FalVideoProvider):
    """第二家生影片 Provider,驗證抽象成立(fal.ai Wan image-to-video)。"""

    name = "fal-wan"
    unit_cost_usd = 0.20
    endpoint = "fal-ai/wan-i2v"


def generate_clips(
    req: VideoRequest,
    out_paths: list[Path],
    cfg: Config,
    costs: list[CostEntry],
    start: int = 0,
) -> list[Path]:
    """統一入口:依 `cfg.video_provider` 選 Provider,產出多段候選。"""
    return get_video_provider(cfg.video_provider).generate(req, out_paths, cfg, costs, start)


def generate_clip(
    shot: Shot,
    image_path: Path,
    out_path: Path,
    cfg: Config,
    costs: list[CostEntry],
    variant: int = 0,
) -> Path:
    """單段生影片的相容包裝(routing / 舊呼叫端用)。variant 產生不同運鏡候選。"""
    req = VideoRequest(
        image_path=image_path,
        duration=shot.duration,
        motion_hint=shot.motion_hint or shot.description,
        shot_index=shot.index,
    )
    return generate_clips(req, [out_path], cfg, costs, start=variant)[0]


def _upload_image(image_path: Path, fal_key: str) -> str:
    """把本地圖片上傳到 fal 儲存,拿到公開 URL 供 image-to-video 使用。"""
    try:
        import httpx
    except ImportError as exc:  # noqa: TRY003
        raise RuntimeError("需要 httpx 上傳圖片:pip install httpx。") from exc

    with httpx.Client(timeout=120.0, headers={"Authorization": f"Key {fal_key}"}) as http:
        resp = http.post(
            "https://fal.run/storage/upload",
            files={"file": (image_path.name, image_path.read_bytes(), "image/png")},
        )
        resp.raise_for_status()
        return resp.json()["url"]


def extend_clip_with_provider(
    src_path: Path,
    out_path: Path,
    cfg: Config,
    costs: list[CostEntry],
    *,
    extend_seconds: float = 5.0,
) -> Path:
    """統一入口:依 `cfg.video_provider` 延伸已選影片。"""
    return get_video_provider(cfg.video_provider).extend(
        src_path, out_path, cfg, costs, extend_seconds=extend_seconds
    )
