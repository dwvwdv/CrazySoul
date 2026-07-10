"""Phase 0 管線編排:打通單一路徑。

流程(對應 README「實作階段建議」的 Phase 0):
  主題 → [1] Storyboard(LLM)→ 逐分鏡 [3] 生圖 → [5a] 生成影片(先不分流)
       → [7] FFmpeg 硬串接 → 產出最終 MP4 →(手動丟 pCloud)

目標是驗證資料流,不追求成本優化,也不做 Web UI。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import Config
from .ffmpeg import concat_clips
from .models import Character, CostEntry, RunResult, ShotResult
from .providers.image import generate_image
from .routing import decide_routes, render_clip
from .storyboard import generate_storyboard


def run_pipeline(
    prompt: str,
    cfg: Config,
    num_shots: int = 3,
    characters: list[Character] | None = None,
) -> RunResult:
    """跑一次完整 Phase 0 管線,回傳結果與產物路徑。

    `characters`:Phase 2 角色庫;分鏡標記的出場角色會在生圖時自動帶入。
    """
    char_map = {c.name: c for c in (characters or [])}
    run_dir = cfg.output_root / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    costs: list[CostEntry] = []

    # [1] 分鏡
    _log("產生分鏡…")
    storyboard = generate_storyboard(prompt, cfg, costs, num_shots=num_shots)
    (run_dir / "storyboard.json").write_text(
        json.dumps(storyboard.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _log(f"  → 《{storyboard.title}》共 {len(storyboard.shots)} 個分鏡")

    # [2] Routing Decision:依 needs_motion + 動態比例上限,決定每個分鏡走哪條路徑
    routes = decide_routes(storyboard.shots, cfg.dynamic_ratio)
    dyn = sum(1 for r in routes if r == "video")
    _log(f"  → 分流:{dyn} 動態(Video Provider)/ {len(routes) - dyn} 靜態(Motion Engine)")

    # [3][5] 逐分鏡生圖 + 依路徑生成影片
    shot_results: list[ShotResult] = []
    for shot in storyboard.shots:
        route = routes[shot.index]
        shot_chars = [char_map[n] for n in shot.characters if n in char_map]
        _log(f"分鏡 {shot.index + 1}/{len(storyboard.shots)}:生圖…")
        image_path = generate_image(
            shot,
            run_dir / "images" / f"shot_{shot.index:02d}.png",
            cfg,
            costs,
            characters=shot_chars,
        )
        path_label = "動態 Video Provider" if route == "video" else "靜態 Motion Engine"
        _log(f"分鏡 {shot.index + 1}/{len(storyboard.shots)}:生成影片({path_label})…")
        clip_path = render_clip(
            shot, image_path, run_dir / "clips" / f"shot_{shot.index:02d}.mp4", cfg, costs, route
        )
        shot_results.append(ShotResult(shot=shot, image_path=str(image_path), clip_path=str(clip_path)))

        _check_budget(cfg, costs)

    # [7] 串接
    _log("FFmpeg 串接最終影片…")
    final_video = run_dir / "final.mp4"
    concat_clips([Path(r.clip_path) for r in shot_results], final_video)

    # 成本紀錄(對應 Supabase cost_log,Phase 0 先落地成檔案)
    (run_dir / "cost_log.json").write_text(
        json.dumps([c.to_dict() for c in costs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = RunResult(
        run_dir=str(run_dir),
        storyboard=storyboard,
        shot_results=shot_results,
        final_video=str(final_video),
        costs=costs,
    )
    _log(f"完成:{final_video}(估算成本 ${result.total_cost_usd})")
    _log("下一步(Phase 0 手動):把 final.mp4 上傳到 pCloud。")
    return result


def _check_budget(cfg: Config, costs: list[CostEntry]) -> None:
    """成本護欄雛形(Phase 7 完整實作):超過上限就中止。"""
    if cfg.cost_limit_usd <= 0:
        return
    spent = sum(c.unit_cost_usd for c in costs) * cfg.cost_retry_factor
    if spent > cfg.cost_limit_usd:
        raise RuntimeError(
            f"預估成本 ${spent:.2f}(含 ×{cfg.cost_retry_factor} 重試係數)"
            f"超過上限 ${cfg.cost_limit_usd:.2f},中止。"
        )


def _log(msg: str) -> None:
    print(f"[crazysoul] {msg}", flush=True)
