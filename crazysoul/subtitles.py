"""字幕時間軸與燒字幕工具。

Phase 5 先提供可離線測試的字幕路徑:dry-run 依文字切句產生 SRT;live 模式若有
OpenAI key 與音訊檔,可用 Whisper verbose_json segments 取得較接近真實語音的時間軸。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Config
from .ffmpeg import run as ffmpeg_run
from .models import CostEntry


@dataclass(frozen=True)
class SubtitleCue:
    """單段字幕 cue,使用秒數保存時間區間。"""

    start: float
    end: float
    text: str


def generate_subtitle_timeline(
    text: str,
    out_path: Path,
    cfg: Config,
    costs: list[CostEntry],
    *,
    duration: float,
    audio_path: Path | None = None,
) -> list[SubtitleCue]:
    """產生 SRT 字幕時間軸並回傳 cue 清單。

    dry-run 或沒有音訊/憑證時使用文字切句平均分配時間;live 模式有音訊與 OpenAI key 時,
    透過 Whisper transcription segments 取得時間軸。
    """
    clean = text.strip()
    if not clean:
        raise ValueError("subtitle text cannot be empty")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cues: list[SubtitleCue]
    if not cfg.dry_run and cfg.openai_api_key and audio_path and audio_path.is_file():
        cues = _whisper_segments(audio_path, cfg, costs)
        if not cues:
            cues = _heuristic_cues(clean, duration)
    else:
        cues = _heuristic_cues(clean, duration)
        costs.append(CostEntry("subtitle", "dry-run", 0.0, f"heuristic {len(cues)} cues"))

    _write_srt(cues, out_path)
    return cues


def burn_subtitles(video_path: Path, srt_path: Path, out_path: Path) -> Path:
    """把 SRT 字幕燒進影片畫面。"""
    if not srt_path.is_file():
        raise FileNotFoundError(f"subtitle file not found: {srt_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # subtitles filter 需要處理 Windows 磁碟冒號與單引號;Linux 路徑則保留可讀性。
    escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    ffmpeg_run(
        [
            "-i", str(video_path),
            "-vf",
            "subtitles='{}':force_style='FontName=Noto Sans CJK TC,FontSize=18," 
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1," 
            "Outline=2,Shadow=1,Alignment=2,MarginV=120'".format(escaped),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(out_path),
        ]
    )
    return out_path


def _whisper_segments(audio_path: Path, cfg: Config, costs: list[CostEntry]) -> list[SubtitleCue]:
    """用 OpenAI Whisper verbose_json segments 產生字幕 cue。"""
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live subtitle alignment")
    with audio_path.open("rb") as fh:
        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {cfg.openai_api_key}"},
            data={"model": "whisper-1", "response_format": "verbose_json"},
            files={"file": (audio_path.name, fh, "application/octet-stream")},
            timeout=180.0,
        )
    response.raise_for_status()
    payload = response.json()
    cues = [
        SubtitleCue(float(seg.get("start", 0.0)), float(seg.get("end", 0.0)), str(seg.get("text", "")).strip())
        for seg in payload.get("segments", [])
        if str(seg.get("text", "")).strip()
    ]
    costs.append(CostEntry("subtitle", "openai-whisper", 0.0, f"{len(cues)} cues"))
    return cues


def _heuristic_cues(text: str, duration: float) -> list[SubtitleCue]:
    parts = [p.strip() for p in re.split(r"(?<=[。！？!?\.])\s*|\n+", text) if p.strip()]
    if not parts:
        parts = [text]
    total_chars = sum(max(1, len(p)) for p in parts)
    cursor = 0.0
    cues: list[SubtitleCue] = []
    safe_duration = max(1.0, duration)
    for idx, part in enumerate(parts):
        if idx == len(parts) - 1:
            end = safe_duration
        else:
            share = max(1, len(part)) / total_chars
            end = cursor + safe_duration * share
        # 套用最短 0.25s 後夾回影片長度,cursor 前進到實際輸出的 end,保持時間軸單調
        end = min(safe_duration, max(cursor + 0.25, end))
        cues.append(SubtitleCue(cursor, end, part))
        cursor = end
    return cues


def _write_srt(cues: list[SubtitleCue], out_path: Path) -> None:
    chunks = []
    for idx, cue in enumerate(cues, start=1):
        chunks.append(
            f"{idx}\n{_srt_time(cue.start)} --> {_srt_time(cue.end)}\n{cue.text}\n"
        )
    out_path.write_text("\n".join(chunks), encoding="utf-8")


def _srt_time(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    h, rem = divmod(millis, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
