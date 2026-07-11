"""Phase 5 Audio Layer tests."""

from __future__ import annotations

from pathlib import Path

from crazysoul.audio import synthesize_voiceover
from crazysoul.ffmpeg import run as ffmpeg_run
from crazysoul.config import Config
from crazysoul.models import CostEntry
from crazysoul.pipeline import run_pipeline


def test_tts_dry_run_creates_voiceover(tmp_path):
    costs: list[CostEntry] = []
    out = synthesize_voiceover("這是一段測試旁白", tmp_path / "voiceover.wav", Config(dry_run=True), costs)
    assert out.exists() and out.stat().st_size > 0
    assert costs[0].stage == "tts"
    assert costs[0].provider == "dry-run"


def test_pipeline_can_mux_dry_run_voiceover(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    result = run_pipeline("測試主題:有旁白的短片", cfg, num_shots=1, voiceover_text="開場旁白")
    assert result.final_video.endswith("final_with_voiceover.mp4")
    assert Path(result.final_video).exists() and Path(result.final_video).stat().st_size > 0
    assert any(c.stage == "tts" for c in result.costs)


def _make_test_music(path: Path, duration: float = 2.0) -> Path:
    ffmpeg_run([
        "-f", "lavfi",
        "-i", f"sine=frequency=220:sample_rate=44100:duration={duration:.3f}",
        "-c:a", "pcm_s16le",
        str(path),
    ])
    return path


def test_pipeline_can_mux_background_music(tmp_path):
    music = _make_test_music(tmp_path / "music.wav")
    cfg = Config(dry_run=True, output_root=tmp_path / "runs")
    result = run_pipeline("測試主題:有背景音樂的短片", cfg, num_shots=1, background_music=music)
    assert result.final_video.endswith("final_with_music.mp4")
    assert Path(result.final_video).exists() and Path(result.final_video).stat().st_size > 0
    assert any(c.stage == "music" for c in result.costs)


def test_pipeline_can_mix_voiceover_and_background_music(tmp_path):
    music = _make_test_music(tmp_path / "music.wav")
    cfg = Config(dry_run=True, output_root=tmp_path / "runs")
    result = run_pipeline(
        "測試主題:旁白加背景音樂",
        cfg,
        num_shots=1,
        voiceover_text="開場旁白",
        background_music=music,
    )
    assert result.final_video.endswith("final_with_voiceover_and_music.mp4")
    assert Path(result.final_video).exists() and Path(result.final_video).stat().st_size > 0
    stages = {c.stage for c in result.costs}
    assert {"tts", "music"}.issubset(stages)
