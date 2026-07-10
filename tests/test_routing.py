"""Phase 1 Routing Decision 的單元測試與混合路徑端到端測試。

不需要憑證或網路,只需要 ffmpeg(系統或 imageio-ffmpeg)。
"""

from __future__ import annotations

from crazysoul.config import Config
from crazysoul.models import CostEntry, Shot
from crazysoul.pipeline import run_pipeline
from crazysoul.routing import decide_routes, dynamic_budget, render_clip


def _shots(flags: list[bool]) -> list[Shot]:
    return [
        Shot(index=i, description=f"d{i}", needs_motion=f) for i, f in enumerate(flags)
    ]


# ---- decide_routes ----
def test_route_follows_needs_motion_at_full_ratio():
    routes = decide_routes(_shots([True, False, True]), dynamic_ratio=1.0)
    assert routes == ["video", "motion", "video"]


def test_static_shots_never_go_video():
    # needs_motion=False 的分鏡即使額度充足也不會走 video
    routes = decide_routes(_shots([False, False]), dynamic_ratio=1.0)
    assert routes == ["motion", "motion"]


def test_ratio_zero_forces_all_motion():
    routes = decide_routes(_shots([True, True, True]), dynamic_ratio=0.0)
    assert routes == ["motion", "motion", "motion"]


def test_ratio_caps_dynamic_count_prefers_earlier():
    # 4 個都要動態,但額度上限 = round(0.5×4)=2 → 只有前兩個走 video
    routes = decide_routes(_shots([True, True, True, True]), dynamic_ratio=0.5)
    assert routes == ["video", "video", "motion", "motion"]


def test_budget_helper_rounds():
    assert dynamic_budget(3, 1.0) == 3
    assert dynamic_budget(3, 0.0) == 0
    assert dynamic_budget(4, 0.5) == 2


def test_decide_routes_empty():
    assert decide_routes([], dynamic_ratio=0.5) == []


# ---- render_clip 依路徑記帳 ----
def test_render_clip_motion_is_zero_cost(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    costs: list[CostEntry] = []
    shot = Shot(index=0, description="d", needs_motion=False)
    img = tmp_path / "a.png"
    from crazysoul import ffmpeg

    ffmpeg.make_placeholder_image(img, label="d", seed=1)
    out = render_clip(shot, img, tmp_path / "clip.mp4", cfg, costs, route="motion")
    assert out.exists() and out.stat().st_size > 0
    assert costs[-1].provider == "motion-engine"
    assert costs[-1].unit_cost_usd == 0.0


# ---- 混合路徑端到端 ----
def test_mixed_route_pipeline_produces_final(tmp_path):
    # dry-run 分鏡 needs_motion 交錯:0,2,4=True / 1,3=False
    cfg = Config(dry_run=True, output_root=tmp_path, dynamic_ratio=1.0)
    result = run_pipeline("混合路徑測試", cfg, num_shots=4)

    final_files = list(tmp_path.rglob("final.mp4"))
    assert len(final_files) == 1 and final_files[0].stat().st_size > 0
    assert len(result.shot_results) == 4

    # 應同時出現 video(動態)與 motion-engine(靜態)兩種路徑的成本紀錄
    video_providers = {c.provider for c in result.costs if c.stage == "video"}
    assert "motion-engine" in video_providers  # 有靜態分鏡走 Motion Engine


def test_ratio_zero_pipeline_all_motion(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path, dynamic_ratio=0.0)
    result = run_pipeline("全靜態測試", cfg, num_shots=3)
    video_costs = [c for c in result.costs if c.stage == "video"]
    assert video_costs and all(c.provider == "motion-engine" for c in video_costs)
