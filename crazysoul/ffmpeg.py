"""FFmpeg 封裝。

README 指定影片合成一律用 FFmpeg(subprocess 呼叫),不引入 Godot/Remotion。
這裡集中所有 ffmpeg 呼叫,並負責解析 ffmpeg 執行檔位置:
優先用系統 PATH 上的 ffmpeg,找不到就退回 imageio-ffmpeg 內建 binary。
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    """回傳可用的 ffmpeg 執行檔路徑。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001 - 給出可行動的錯誤訊息
        raise FFmpegError(
            "找不到 ffmpeg。請安裝系統 ffmpeg,或 `pip install imageio-ffmpeg`。"
        ) from exc


def run(args: list[str]) -> None:
    """執行一次 ffmpeg,失敗時把 stderr 收進例外。"""
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(
            f"ffmpeg 失敗(exit {proc.returncode}):\n"
            f"cmd: {' '.join(cmd)}\n{proc.stderr.strip()}"
        )


# 直式短影音的標準畫布(對應 YouTube Shorts / Reels 的 9:16)
WIDTH, HEIGHT, FPS = 1080, 1920, 30


def make_placeholder_image(out_path: Path, label: str, seed: int) -> None:
    """dry-run 用:產生一張純色佔位圖,代替真正的 Image Provider。

    用 ffmpeg 的 lavfi color source,不依賴 PIL。顏色由 seed 決定,方便肉眼分辨
    不同分鏡與同一分鏡的不同候選(縮圖牆挑選)。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    hue = (seed * 47) % 360
    run(
        [
            "-f", "lavfi",
            "-i", f"color=c=gray:s={WIDTH}x{HEIGHT}",
            "-vf", f"hue=h={hue}:s=1.2,format=rgb24",
            "-frames:v", "1",
            str(out_path),
        ]
    )


def image_to_motion_clip(
    image_path: Path, out_path: Path, duration: float, variant: int = 0
) -> None:
    """把靜態圖做成「看起來在動」的影片片段(Motion Engine 的 zoompan)。

    Phase 0 的 dry-run 用它代替 Video Provider;Phase 1 之後這就是 5b 靜態路徑的實作基礎。
    variant 讓同一張圖的多個候選有不同運鏡(推近 / 拉遠 / 較快推近),方便縮圖牆挑選。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, int(round(duration * FPS)))
    # 依 variant 選運鏡:0=緩慢推近,1=緩慢拉遠,其餘=較快推近。
    if variant % 3 == 1:
        z_expr = "max(1.15-0.0008*on,1.0)"  # zoom-out
    elif variant % 3 == 2:
        z_expr = "min(zoom+0.0016,1.30)"     # 較快推近
    else:
        z_expr = "min(zoom+0.0008,1.15)"     # 緩慢推近
    zoompan = (
        f"scale={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='{z_expr}':d={total_frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={WIDTH}x{HEIGHT}:fps={FPS}"
    )
    run(
        [
            "-loop", "1",
            "-i", str(image_path),
            "-t", f"{duration:.3f}",
            "-vf", zoompan,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            str(out_path),
        ]
    )


def normalize_clip(src: Path, out_path: Path, duration: float | None = None) -> None:
    """把外部 Provider 回傳的影片統一成標準畫布/編碼,方便後續無痛串接。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},fps={FPS}"
    )
    args = ["-i", str(src), "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    run([*args, str(out_path)])


def silent_audio(out_path: Path, duration: float) -> None:
    """Create a silent AAC track for dry-run narration placeholders."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{duration:.3f}",
        "-c:a", "aac",
        str(out_path),
    ])


def add_audio_subtitles(
    video_path: Path,
    audio_path: Path | None,
    subtitles_path: Path | None,
    out_path: Path,
) -> None:
    """Add optional audio and burned-in subtitles to a video."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(video_path)]
    if audio_path is not None:
        args += ["-i", str(audio_path)]
    vf = []
    if subtitles_path is not None:
        escaped = str(subtitles_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf.append(f"subtitles='{escaped}'")
    if vf:
        args += ["-vf", ",".join(vf)]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio_path is not None:
        args += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-shortest"]
    else:
        args += ["-an"]
    run([*args, str(out_path)])


def extend_clip(src: Path, out_path: Path, extra_seconds: float) -> None:
    """Extend a clip by freezing its last frame."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "-i", str(src),
        "-vf", f"tpad=stop_mode=clone:stop_duration={extra_seconds:.3f}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ])


def concat_clips(clips: list[Path], out_path: Path) -> None:
    """把多個標準化後的片段硬串接成最終影片(Composition Engine 的核心)。"""
    if not clips:
        raise FFmpegError("沒有可串接的片段。")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    listfile = out_path.parent / "_concat.txt"
    listfile.write_text(
        "".join(f"file '{c.resolve().as_posix()}'\n" for c in clips),
        encoding="utf-8",
    )
    run(
        [
            "-f", "concat",
            "-safe", "0",
            "-i", str(listfile),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
    )
    listfile.unlink(missing_ok=True)
