"""Phase 5 字幕時間軸與燒字幕測試。"""

from __future__ import annotations

from pathlib import Path

from crazysoul.config import Config
from crazysoul.ffmpeg import image_to_motion_clip, make_placeholder_image
from crazysoul.models import CostEntry
from crazysoul.pipeline import run_pipeline
from crazysoul.subtitles import burn_subtitles, generate_subtitle_timeline


def test_generate_subtitle_timeline_writes_srt(tmp_path):
    costs: list[CostEntry] = []
    out = tmp_path / "captions.srt"
    cues = generate_subtitle_timeline(
        "第一句。第二句！", out, Config(dry_run=True), costs, duration=4.0
    )
    text = out.read_text(encoding="utf-8")
    assert len(cues) == 2
    assert "00:00:00,000 -->" in text
    assert "第一句。" in text
    assert costs[0].stage == "subtitle"


def test_burn_subtitles_creates_video(tmp_path):
    img = tmp_path / "img.png"
    video = tmp_path / "clip.mp4"
    srt = tmp_path / "captions.srt"
    out = tmp_path / "subtitled.mp4"
    make_placeholder_image(img, "字幕", 7)
    image_to_motion_clip(img, video, 1.0)
    generate_subtitle_timeline("字幕測試", srt, Config(dry_run=True), [], duration=1.0)
    burn_subtitles(video, srt, out)
    assert out.exists() and out.stat().st_size > 0


def test_pipeline_can_burn_subtitles(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    result = run_pipeline("測試主題:有字幕的短片", cfg, num_shots=1, subtitle_text="開場字幕。結尾字幕。")
    assert result.final_video.endswith("final_with_subtitles.mp4")
    assert Path(result.final_video).exists() and Path(result.final_video).stat().st_size > 0
    assert any(c.stage == "subtitle" for c in result.costs)
