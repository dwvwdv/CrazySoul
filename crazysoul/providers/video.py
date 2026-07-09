"""[5a] Video Provider Layer — Phase 0 主力:Kling via fal.ai(image-to-video)。

介面:generate_clip(shot, image_path, out_path, cfg, costs) → 產出一段標準化影片。
Phase 0 不分流,所有分鏡都走這條(README Phase 0 說明:先不分流)。
dry-run 用 FFmpeg Motion Engine(zoompan)代替,零成本驗證資料流。
"""

from __future__ import annotations

from pathlib import Path

from .. import ffmpeg
from ..config import Config
from ..models import CostEntry, Shot
from . import falai

# Kling (fal.ai) 粗估單價(每段 5 秒),實際以帳單為準。
_KLING_UNIT_USD = 0.28


def generate_clip(
    shot: Shot,
    image_path: Path,
    out_path: Path,
    cfg: Config,
    costs: list[CostEntry],
) -> Path:
    if cfg.dry_run:
        ffmpeg.image_to_motion_clip(image_path, out_path, shot.duration)
        costs.append(CostEntry("video", "dry-run(motion-engine)", 0.0, f"分鏡{shot.index}"))
        return out_path

    if cfg.video_provider != "fal-kling":
        raise NotImplementedError(
            f"目前只實作 fal-kling 影片 Provider(收到 {cfg.video_provider!r})。"
        )
    if not cfg.fal_key:
        raise RuntimeError("未設定 FAL_KEY(或改用 --dry-run)。")

    # fal.ai 需要可存取的圖片 URL;Phase 0 先上傳到 fal 儲存再餵給 Kling。
    image_url = _upload_image(image_path, cfg.fal_key)
    result = falai.run_model(
        cfg.fal_key,
        endpoint="fal-ai/kling-video/v1/standard/image-to-video",
        payload={
            "prompt": shot.motion_hint or shot.description,
            "image_url": image_url,
            "duration": str(int(round(shot.duration))),
        },
    )
    raw = out_path.with_name(out_path.stem + "_raw.mp4")
    falai.download(result["video"]["url"], raw, cfg.fal_key)
    # 統一畫布/編碼,確保後續 concat 無縫。
    ffmpeg.normalize_clip(raw, out_path, duration=shot.duration)
    raw.unlink(missing_ok=True)
    costs.append(CostEntry("video", "fal-kling", _KLING_UNIT_USD, f"分鏡{shot.index}"))
    return out_path


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
