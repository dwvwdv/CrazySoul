"""Phase 0 dry-run 端到端測試。

不需要任何憑證或網路,只需要 ffmpeg(系統或 imageio-ffmpeg)。
驗證:分鏡 → 生圖 → 生成影片 → 串接 的資料流能完整跑通並產出 final.mp4。
"""

from __future__ import annotations

import json

from crazysoul.config import Config
from crazysoul.models import Shot, Storyboard
from crazysoul.pipeline import run_pipeline


def test_dry_run_produces_final_video(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    result = run_pipeline("測試主題:雨中的紅傘", cfg, num_shots=3)

    final = tmp_path.rglob("final.mp4")
    final_files = list(final)
    assert len(final_files) == 1
    assert final_files[0].stat().st_size > 0

    # 每個分鏡都要有圖與影片
    assert len(result.shot_results) == 3
    for r in result.shot_results:
        assert r.image_path.endswith(".png")
        assert r.clip_path.endswith(".mp4")

    # dry-run 成本為 0
    assert result.total_cost_usd == 0.0


def test_storyboard_json_written(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    result = run_pipeline("測試主題", cfg, num_shots=2)

    sb_file = next(iter(tmp_path.rglob("storyboard.json")))
    data = json.loads(sb_file.read_text(encoding="utf-8"))
    assert data["prompt"] == "測試主題"
    assert len(data["shots"]) == 2

    cost_file = next(iter(tmp_path.rglob("cost_log.json")))
    costs = json.loads(cost_file.read_text(encoding="utf-8"))
    stages = {c["stage"] for c in costs}
    assert {"storyboard", "image", "video"} <= stages


def test_shot_from_dict_defaults():
    shot = Shot.from_dict({"description": "  近景一隻貓  "}, index=1)
    assert shot.index == 1
    assert shot.description == "近景一隻貓"
    assert shot.shot_type == "medium"
    assert shot.needs_motion is True
    assert shot.duration == 5.0


def test_storyboard_to_dict_roundtrip():
    sb = Storyboard(
        prompt="p",
        title="t",
        shots=[Shot(index=0, description="d")],
    )
    d = sb.to_dict()
    assert d["title"] == "t"
    assert d["shots"][0]["description"] == "d"
