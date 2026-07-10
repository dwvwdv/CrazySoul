"""[Phase 1] Routing Decision — 降成本核心。

依 storyboard 的 `needs_motion` 把每個分鏡分流到兩條路徑:
  - `video`  :需要真實動態 → 走付費 Video Provider(Kling 等)。
  - `motion` :靜態即可 → 走 Motion Engine(FFmpeg zoompan,零額外成本)。

再疊一層「動態分鏡比例上限」(`dynamic_ratio`):即使 LLM 把很多分鏡標為
需要動態,也只讓最多這個比例的分鏡走付費路徑,其餘退回靜態,用來壓成本。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from . import ffmpeg
from .config import Config
from .models import CostEntry, Shot
from .providers.video import generate_clip

# 兩條路徑:動態(付費 Video Provider)/ 靜態(FFmpeg Motion Engine)。
Route = Literal["video", "motion"]

# Motion Engine 走本地 FFmpeg,無 Provider 費用。
_MOTION_UNIT_USD = 0.0


def dynamic_budget(count: int, dynamic_ratio: float) -> int:
    """在給定分鏡數與比例上限下,最多能有幾個分鏡走 video 路徑。"""
    ratio = min(max(dynamic_ratio, 0.0), 1.0)
    return int(round(ratio * count))


def decide_routes(shots: list[Shot], dynamic_ratio: float = 1.0) -> list[Route]:
    """回傳與 `shots` 等長的路徑清單。

    規則:
      1. 只有 `needs_motion` 的分鏡有資格走 video。
      2. 動態額度 = round(dynamic_ratio × 分鏡數);超過額度的 needs_motion
         分鏡照原順序退回 motion(靠前的分鏡優先取得動態路徑)。
      3. 其餘一律 motion。
    """
    routes: list[Route] = ["motion"] * len(shots)
    budget = dynamic_budget(len(shots), dynamic_ratio)
    eligible = [i for i, s in enumerate(shots) if s.needs_motion]
    for i in eligible[:budget]:
        routes[i] = "video"
    return routes


def render_clip(
    shot: Shot,
    image_path: Path,
    out_path: Path,
    cfg: Config,
    costs: list[CostEntry],
    route: Route,
    variant: int = 0,
) -> Path:
    """依路徑產出一段影片。

    - `video` :交給 Video Provider(dry-run 下同樣退回 Motion Engine)。
    - `motion`:直接用 FFmpeg zoompan,不呼叫付費 Provider,成本記為 0。
    """
    if route == "video":
        return generate_clip(shot, image_path, out_path, cfg, costs, variant=variant)

    ffmpeg.image_to_motion_clip(image_path, out_path, shot.duration, variant=variant)
    costs.append(
        CostEntry("video", "motion-engine", _MOTION_UNIT_USD, f"分鏡{shot.index} 候選{variant}")
    )
    return out_path
