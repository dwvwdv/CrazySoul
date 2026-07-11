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


def test_heuristic_cues_stay_monotonic_within_duration(tmp_path):
    # 短影片配很多短句:最短 0.25s 撐開後,時間軸仍須單調且不超過影片長度
    costs: list[CostEntry] = []
    out = tmp_path / "captions.srt"
    cues = generate_subtitle_timeline(
        "一。二。三。四。五。六。七。八。", out, Config(dry_run=True), costs, duration=1.0
    )
    prev_end = 0.0
    for cue in cues:
        assert cue.start == prev_end  # 下一句從上一句實際結束的時間開始
        assert cue.end >= cue.start
        prev_end = cue.end
    assert cues[-1].end <= 1.0


def test_pipeline_passes_voiceover_audio_to_subtitles(tmp_path, monkeypatch):
    # 有生成配音時,字幕對齊必須拿到音檔(live 模式才能走 Whisper)
    import crazysoul.pipeline as pipeline_mod

    captured: dict = {}
    real = pipeline_mod.generate_subtitle_timeline

    def spy(text, out_path, cfg, costs, *, duration, audio_path=None):
        captured["audio_path"] = audio_path
        return real(text, out_path, cfg, costs, duration=duration, audio_path=audio_path)

    monkeypatch.setattr(pipeline_mod, "generate_subtitle_timeline", spy)
    cfg = Config(dry_run=True, output_root=tmp_path)
    run_pipeline(
        "測試主題", cfg, num_shots=1, voiceover_text="這是旁白。", subtitle_text="這是字幕。"
    )
    assert captured["audio_path"] is not None
    assert captured["audio_path"].is_file()


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
