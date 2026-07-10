"""Audio/subtitle helpers for Phase 5."""

from __future__ import annotations

from pathlib import Path

from . import ffmpeg
from .config import Config
from .models import CostEntry


def synthesize_voice(text: str, out_path: Path, cfg: Config, costs: list[CostEntry]) -> Path:
    """Create a narration track. Dry-run uses silent audio; live TTS is explicitly gated."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(1.0, min(60.0, len(text) / 9.0))
    if cfg.dry_run:
        ffmpeg.silent_audio(out_path, duration)
        costs.append(CostEntry("tts", "dry-run(silence)", 0.0, f"{duration:.1f}s"))
        return out_path
    raise NotImplementedError("TTS provider 尚未設定；請使用 dry-run 或接入 OpenAI/ElevenLabs。")


def make_srt(text: str, out_path: Path, duration: float) -> Path:
    """Write a simple single-cue SRT file; Whisper alignment can replace this later."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(f"1\n00:00:00,000 --> {_srt_ts(duration)}\n{text.strip()}\n", encoding="utf-8")
    return out_path


def compose_audio_subtitles(video: Path, voice: Path | None, subtitles: Path | None, out_path: Path) -> Path:
    """Mux narration and burn subtitles into the final video."""
    ffmpeg.add_audio_subtitles(video, voice, subtitles, out_path)
    return out_path


def _srt_ts(seconds: float) -> str:
    ms = int(max(0, seconds) * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"
