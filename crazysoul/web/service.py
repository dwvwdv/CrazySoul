"""把 Phase 0 的生成模組接到 Web Console 的專案狀態上。

每個函式都是 blocking 的,由 JobManager 丟到背景執行緒執行。
負責:呼叫 Provider、把產物寫到專案媒體目錄、更新 Project 狀態、回傳給前端的結果。
"""

from __future__ import annotations

from pathlib import Path

from ..audio import mux_background_music
from ..config import Config
from ..ffmpeg import concat_clips
from ..guardrails import estimated_spend
from ..models import Character, CostEntry
from ..providers.base import ImageRequest
from ..providers.image import generate_images
from ..providers.video import extend_clip_with_provider
from ..routing import Route, decide_routes, render_clip
from ..storyboard import generate_storyboard
from ..subtitles import burn_subtitles, generate_subtitle_timeline
from ..storage import upload_webdav
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
    # Phase 1:依動態比例上限先算好每個分鏡的預設路徑,使用者可再手動覆寫。
    routes = decide_routes(sb.shots, project.dynamic_ratio)
    project.shots = [
        ShotState(shot=s, stage="need_images", route=routes[s.index]) for s in sb.shots
    ]
    return {"pid": project.pid, "shots": len(project.shots)}


def set_route(project: Project, shot_idx: int, route: Route) -> dict:
    """手動覆寫單一分鏡的分流路徑(video=動態 / motion=靜態)。"""
    if route not in ("video", "motion"):
        raise ValueError(f"未知路徑 {route!r}(只接受 video / motion)。")
    project.shots[shot_idx].route = route
    return {"route": route}


def run_image_candidates(
    cfg: Config, project: Project, shot_idx: int, count: int
) -> dict:
    st = project.shots[shot_idx]
    pdir = project_dir(cfg, project.pid)
    # Phase 2:把分鏡標記的出場角色帶入生圖(seed / style_tag / 參考圖)
    chars = project.resolve_characters(st.shot.characters)
    req = ImageRequest(prompt=st.shot.description, shot_index=shot_idx, characters=chars)
    out_paths = [pdir / f"shot_{shot_idx:02d}/img_{k:02d}.png" for k in range(count)]
    # Phase 3:一次呼叫原生批量產出 count 張候選
    generate_images(req, out_paths, cfg, project.costs)
    st.image_candidates = [
        Candidate(
            cid=f"i{shot_idx}_{k}",
            url=_media_url(project.pid, f"shot_{shot_idx:02d}/img_{k:02d}.png"),
            kind="image",
        )
        for k in range(count)
    ]
    st.selected_image = None
    st.stage = "awaiting_image_pick"
    return {"count": len(st.image_candidates)}


# ---- Phase 2:角色庫 ----
def save_reference_image(cfg: Config, project: Project, name: str, data: bytes, suffix: str) -> str:
    """把角色參考圖存進專案目錄,回傳可存取的相對路徑。"""
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "char"
    rel = f"characters/{safe}{suffix or '.png'}"
    out = project_dir(cfg, project.pid) / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return rel


def add_character(
    project: Project,
    name: str,
    style_tag: str = "",
    seed: int | None = None,
    ref_image: str | None = None,
) -> dict:
    """新增或更新一個角色(以名稱為主鍵)。"""
    name = name.strip()
    if not name:
        raise ValueError("角色名稱不可為空。")
    existing = project.character(name)
    if existing:
        existing.style_tag = style_tag.strip()
        existing.seed = seed
        if ref_image:
            existing.ref_image = ref_image
    else:
        project.characters.append(
            Character(name=name, style_tag=style_tag.strip(), seed=seed, ref_image=ref_image)
        )
    return {"name": name, "count": len(project.characters)}


def set_shot_characters(project: Project, shot_idx: int, names: list[str]) -> dict:
    """標記某分鏡的出場角色(只保留專案裡存在的角色名)。"""
    valid = [n for n in names if project.character(n)]
    project.shots[shot_idx].shot.characters = valid
    return {"characters": valid}


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
    st.extended_video = False
    for k in range(count):
        cid = f"v{shot_idx}_{k}"
        rel = f"shot_{shot_idx:02d}/vid_{k:02d}.mp4"
        out = pdir / rel
        render_clip(st.shot, image_path, out, cfg, project.costs, st.route, variant=k)
        st.video_candidates.append(Candidate(cid=cid, url=_media_url(project.pid, rel), kind="video"))
    st.selected_video = None
    st.stage = "awaiting_video_pick"
    return {"count": len(st.video_candidates)}


def select_video(project: Project, shot_idx: int, cid: str) -> dict:
    st = project.shots[shot_idx]
    if not any(c.cid == cid for c in st.video_candidates):
        raise ValueError(f"找不到影片候選 {cid}")
    st.selected_video = cid
    st.extended_video = False
    st.stage = "done"
    return {"selected": cid}


def extend_selected_video(cfg: Config, project: Project, shot_idx: int, extend_seconds: float = 5.0) -> dict:
    """把已選定的影片片段延伸,並把延伸後檔案設為新的選定候選。"""
    st = project.shots[shot_idx]
    cand = st.selected_video_cand()
    if cand is None:
        raise ValueError("尚未選定影片,無法延伸。")
    pdir = project_dir(cfg, project.pid)
    src = pdir / cand.url.split(f"/media/{project.pid}/", 1)[1]
    rel = f"shot_{shot_idx:02d}/vid_extended.mp4"
    out = pdir / rel
    extend_clip_with_provider(src, out, cfg, project.costs, extend_seconds=extend_seconds)
    cid = f"v{shot_idx}_extended"
    st.video_candidates = [c for c in st.video_candidates if c.cid != cid]
    st.video_candidates.append(Candidate(cid=cid, url=_media_url(project.pid, rel), kind="video"))
    st.selected_video = cid
    st.extended_video = True
    st.stage = "done"
    return {"selected": cid, "extended": True}


def save_background_music(cfg: Config, project: Project, data: bytes, suffix: str) -> dict:
    """保存使用者上傳的背景音樂,供合成 final.mp4 時混入。"""
    if not data:
        raise ValueError("背景音樂檔不可為空。")
    suffix = suffix or ".mp3"
    rel = f"audio/background_music{suffix}"
    out = project_dir(cfg, project.pid) / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    project.background_music = rel
    return {"background_music": _media_url(project.pid, rel)}


def set_subtitle_text(project: Project, text: str) -> dict:
    """設定合成 final.mp4 時要使用的字幕文字。"""
    project.subtitle_text = text.strip()
    project.subtitles = None
    return {"subtitle_text": project.subtitle_text}


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
    composed = pdir / rel
    concat_clips(clips, composed)
    if project.background_music:
        rel = "final_with_music.mp4"
        mux_background_music(composed, pdir / project.background_music, pdir / rel)
        project.costs.append(CostEntry("music", "local-upload", 0.0, project.background_music))
    if project.subtitle_text:
        source = pdir / rel
        srt_rel = "subtitles/captions.srt"
        total_duration = sum(max(0.1, st.shot.duration) for st in project.shots)
        generate_subtitle_timeline(
            project.subtitle_text, pdir / srt_rel, cfg, project.costs, duration=total_duration
        )
        rel = "final_with_subtitles.mp4"
        burn_subtitles(source, pdir / srt_rel, pdir / rel)
        project.subtitles = srt_rel
    project.final_video = _media_url(project.pid, rel)
    return {"final_video": project.final_video}


def cost_summary(cfg: Config, project: Project) -> dict:
    """回傳 Web 成本儀表板所需摘要。"""
    by_stage: dict[str, float] = {}
    for c in project.costs:
        by_stage[c.stage] = round(by_stage.get(c.stage, 0.0) + c.unit_cost_usd, 4)
    raw = round(sum(c.unit_cost_usd for c in project.costs), 4)
    return {
        "raw_cost_usd": raw,
        "estimated_with_retry_usd": estimated_spend(project.costs, cfg),
        "retry_factor": cfg.cost_retry_factor,
        "limit_usd": cfg.cost_limit_usd,
        "by_stage": by_stage,
        "entries": [c.to_dict() for c in project.costs],
    }


def save_to_pcloud(cfg: Config, project: Project) -> dict:
    """把最終影片上傳到 pCloud WebDAV;dry-run 或未設定時保留本地佔位。"""
    if not project.final_video:
        raise ValueError("尚未合成最終影片。")
    if cfg.dry_run or not cfg.pcloud_webdav_url:
        project.saved_to_pcloud = True
        return {"saved": True, "note": "dry-run/未設定 WebDAV,已標記保存佔位"}
    pdir = project_dir(cfg, project.pid)
    rel = project.final_video.split(f"/media/{project.pid}/", 1)[1]
    remote = upload_webdav(pdir / rel, f"{project.pid}-{Path(rel).name}", cfg)
    project.saved_to_pcloud = True
    return {"saved": True, "remote_path": remote}
