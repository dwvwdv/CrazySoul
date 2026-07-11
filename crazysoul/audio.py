"""Audio Layer: TTS voiceover generation and audio/video composition helpers.

Phase 5 starts with a minimal voiceover path:
- dry-run: synthesize a local placeholder WAV with FFmpeg (no network/API cost)
- live: call OpenAI's `/v1/audio/speech` endpoint via httpx
"""

from __future__ import annotations

from pathlib import Path

import httpx

from .config import Config
from .ffmpeg import run as ffmpeg_run
from .models import CostEntry


def synthesize_voiceover(text: str, out_path: Path, cfg: Config, costs: list[CostEntry]) -> Path:
    """Generate narration audio for the final video.

    The returned file is ready to be muxed into the final MP4. In dry-run mode this creates
    a quiet sine-wave placeholder whose duration scales with text length, so tests and local
    demos can validate the audio path without paid APIs.
    """
    clean = text.strip()
    if not clean:
        raise ValueError("voiceover text cannot be empty")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.dry_run:
        duration = _estimate_speech_duration(clean)
        ffmpeg_run(
            [
                "-f", "lavfi",
                "-i", f"sine=frequency=440:sample_rate=44100:duration={duration:.3f}",
                "-af", "volume=0.08",
                "-c:a", "pcm_s16le",
                str(out_path),
            ]
        )
        costs.append(CostEntry("tts", "dry-run", 0.0, f"placeholder voiceover {duration:.1f}s"))
        return out_path

    if cfg.tts_provider != "openai-tts":
        raise ValueError(f"unsupported TTS provider: {cfg.tts_provider}")
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live OpenAI TTS")

    response = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {cfg.openai_api_key}"},
        json={
            "model": cfg.tts_model,
            "voice": cfg.tts_voice,
            "input": clean,
            "response_format": out_path.suffix.lstrip(".") or "mp3",
        },
        timeout=120.0,
    )
    response.raise_for_status()
    out_path.write_bytes(response.content)
    costs.append(CostEntry("tts", cfg.tts_provider, cfg.tts_cost_usd, cfg.tts_model))
    return out_path


def mux_voiceover(video_path: Path, audio_path: Path, out_path: Path) -> Path:
    """Mux generated voiceover onto a video while preserving the video stream."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_run(
        [
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(out_path),
        ]
    )
    return out_path


def _estimate_speech_duration(text: str) -> float:
    # Mandarin/Japanese-style prompts often have few spaces, so use a character-based
    # lower-bound estimate rather than word count only.
    return max(1.0, min(60.0, len(text) / 6.0))
