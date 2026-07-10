"""把 Phase 0 的生成模組接到 Web Console 的專案狀態上。

每個函式都是 blocking 的,由 JobManager 丟到背景執行緒執行。
負責:呼叫 Provider、把產物寫到專案媒體目錄、更新 Project 狀態、回傳給前端的結果。
"""

from __future__ import annotations

from pathlib import Path

from ..audio import compose_audio_subtitles, make_srt, synthesize_voice
from ..config import Config
from ..ffmpeg import concat_clips, image_to_motion_clip
from ..pcloud import upload_file
from ..providers.image import generate_image
from ..providers.video import extend_clip, generate_clip
from ..storyboard import generate_storyboard
from .store import Candidate, Project, ShotState


def project_dir(cfg: Config, pid: str) -> Path:
    d = cfg.output_root / "web" / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _media_url(pid: str, rel: str) -> str:
    return f"/media/{pid}/{rel}"


def run_storyboard(cfg: Config, project: Project) -> dict:
    sb = generate_storyboard(project.prompt, cfg, project.costs, num_shots=project.num_shots)
    project.title = sb.title
    project.shots = [ShotState(shot=s, stage="need_images") for s in sb.shots]
    return {"pid": project.pid, "shots": len(project.shots)}


def run_image_candidates(
    cfg: Config, project: Project, shot_idx: int, count: int
) -> dict:
    st = project.shots[shot_idx]
    pdir = project_dir(cfg, project.pid)
    st.image_candidates = []
    for k in range(count):
        cid = f"i{shot_idx}_{k}"
        rel = f"shot_{shot_idx:02d}/img_{k:02d}.png"
        out = pdir / rel
        generate_image(st.shot, out, cfg, project.costs, variant=k)
        st.image_candidates.append(
            Candidate(cid=cid, url=_media_url(project.pid, rel), kind="image")
        )
    st.selected_image = None
    st.stage = "awaiting_image_pick"
    return {"count": len(st.image_candidates)}


def select_image(project: Project, shot_idx: int, cid: str) -> dict:
    st = project.shots[shot_idx]
    if not any(c.cid == cid for c in st.image_candidates):
        raise ValueError(f"找不到圖片候選 {cid}")
    st.selected_image = cid
    st.stage = "need_videos"
    return {"selected": cid}


def run_video_candidates(
    cfg: Config, project: Project, shot_idx: int, count: int
) -> dict:
    st = project.shots[shot_idx]
    chosen = st.selected_image_cand()
    if chosen is None:
        raise ValueError("尚未選定圖片,無法生成影片。")
    pdir = project_dir(cfg, project.pid)
    # 從 URL 反推本地圖片路徑
    image_path = pdir / chosen.url.split(f"/media/{project.pid}/", 1)[1]
    st.video_candidates = []
    for k in range(count):
        cid = f"v{shot_idx}_{k}"
        rel = f"shot_{shot_idx:02d}/vid_{k:02d}.mp4"
        out = pdir / rel
        if st.shot.needs_motion:
            generate_clip(st.shot, image_path, out, cfg, project.costs, variant=k)
        else:
            image_to_motion_clip(image_path, out, st.shot.duration, variant=k)
        st.video_candidates.append(
            Candidate(cid=cid, url=_media_url(project.pid, rel), kind="video")
        )
    st.selected_video = None
    st.stage = "awaiting_video_pick"
    return {"count": len(st.video_candidates)}


def select_video(project: Project, shot_idx: int, cid: str) -> dict:
    st = project.shots[shot_idx]
    if not any(c.cid == cid for c in st.video_candidates):
        raise ValueError(f"找不到影片候選 {cid}")
    st.selected_video = cid
    st.stage = "done"
    return {"selected": cid}


def run_compose(cfg: Config, project: Project) -> dict:
    if not project.shots or not all(s.stage == "done" for s in project.shots):
        raise ValueError("還有分鏡尚未選定影片,無法合成。")
    pdir = project_dir(cfg, project.pid)
    clips: list[Path] = []
    for st in project.shots:
        cand = st.selected_video_cand()
        assert cand is not None
        clips.append(pdir / cand.url.split(f"/media/{project.pid}/", 1)[1])
    rel = "final.mp4"
    concat_clips(clips, pdir / rel)
    project.final_video = _media_url(project.pid, rel)
    return {"final_video": project.final_video}


def run_audio_subtitles(cfg: Config, project: Project, narration: str | None = None) -> dict:
    if not project.final_video:
        raise ValueError("尚未合成最終影片。")
    pdir = project_dir(cfg, project.pid)
    text = narration or project.prompt
    voice_rel = "audio/voiceover.m4a"
    sub_rel = "subtitles/captions.srt"
    out_rel = "final_with_audio.mp4"
    voice = synthesize_voice(text, pdir / voice_rel, cfg, project.costs)
    duration = sum(s.shot.duration for s in project.shots) or 5.0
    subs = make_srt(text, pdir / sub_rel, duration)
    final_rel = project.final_video.split(f"/media/{project.pid}/", 1)[1]
    compose_audio_subtitles(pdir / final_rel, voice, subs, pdir / out_rel)
    project.voiceover = _media_url(project.pid, voice_rel)
    project.subtitles = _media_url(project.pid, sub_rel)
    project.final_with_audio = _media_url(project.pid, out_rel)
    return {
        "voiceover": project.voiceover,
        "subtitles": project.subtitles,
        "final_video": project.final_with_audio,
    }


def run_extend_video(cfg: Config, project: Project, shot_idx: int, seconds: float = 5.0) -> dict:
    st = project.shots[shot_idx]
    cand = st.selected_video_cand()
    if cand is None:
        raise ValueError("尚未選定影片,無法延伸。")
    pdir = project_dir(cfg, project.pid)
    src_rel = cand.url.split(f"/media/{project.pid}/", 1)[1]
    rel = f"shot_{shot_idx:02d}/extended_{len(st.video_candidates):02d}.mp4"
    extend_clip(pdir / src_rel, pdir / rel, cfg, project.costs, seconds=seconds)
    cid = f"v{shot_idx}_ext{len(st.video_candidates)}"
    st.video_candidates.append(Candidate(cid=cid, url=_media_url(project.pid, rel), kind="video"))
    st.selected_video = cid
    st.stage = "done"
    return {"selected": cid, "url": _media_url(project.pid, rel)}


def cost_dashboard(project: Project) -> dict:
    by_stage: dict[str, float] = {}
    for c in project.costs:
        by_stage[c.stage] = round(by_stage.get(c.stage, 0.0) + c.unit_cost_usd, 4)
    return {
        "total_cost_usd": round(sum(by_stage.values()), 4),
        "by_stage": by_stage,
        "entries": [c.to_dict() for c in project.costs],
    }


def save_to_pcloud(project: Project, cfg: Config | None = None) -> dict:
    """Upload the composed video to pCloud WebDAV, or mark dry-run saves."""
    if not project.final_video:
        raise ValueError("尚未合成最終影片。")
    project.saved_to_pcloud = True
    if cfg is None:
        return {"saved": True, "note": "pCloud WebDAV 未提供設定；只標記保存。"}
    pdir = project_dir(cfg, project.pid)
    rel = (project.final_with_audio or project.final_video).split(f"/media/{project.pid}/", 1)[1]
    upload = upload_file(pdir / rel, f"{project.pid}.mp4", cfg)
    return {"saved": True, **upload}
