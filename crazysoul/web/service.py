"""把 Phase 0 的生成模組接到 Web Console 的專案狀態上。

每個函式都是 blocking 的,由 JobManager 丟到背景執行緒執行。
負責:呼叫 Provider、把產物寫到專案媒體目錄、更新 Project 狀態、回傳給前端的結果。
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..ffmpeg import concat_clips
from ..providers.image import generate_image
from ..routing import Route, decide_routes, render_clip
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
    st.image_candidates = []
    for k in range(count):
        cid = f"i{shot_idx}_{k}"
        rel = f"shot_{shot_idx:02d}/img_{k:02d}.png"
        out = pdir / rel
        generate_image(st.shot, out, cfg, project.costs, variant=k)
        st.image_candidates.append(Candidate(cid=cid, url=_media_url(project.pid, rel), kind="image"))
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


def save_to_pcloud(project: Project) -> dict:
    """Phase 0/4:「保存至 pCloud」為主要動作。實際 WebDAV 上傳留待 Phase 6,
    這裡先標記完成,讓主流程走得通(README:先跑通,再抽象)。"""
    if not project.final_video:
        raise ValueError("尚未合成最終影片。")
    project.saved_to_pcloud = True
    return {"saved": True, "note": "pCloud WebDAV 實際上傳留待 Phase 6"}
