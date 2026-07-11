"""Phase 5 Audio Layer tests."""

from __future__ import annotations

from pathlib import Path

from crazysoul.audio import synthesize_voiceover
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
