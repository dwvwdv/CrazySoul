"""Web Console 的專案狀態(記憶體版)。

Phase 4 先用記憶體保存進行中的專案;Phase 之後接 Supabase 時,
這些 dataclass 就是對應 `projects` / `storyboards` / `assets` 的雛形。

對應 README「jobs 表新增 awaiting_selection 狀態」:每個生成節點完成後,
分鏡會停在等待人工挑選的狀態,使用者點選後才往下一步。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Literal

from ..models import Character, CostEntry, Shot
from ..routing import Route

# 分鏡在主線上的狀態機
ShotStage = Literal[
    "pending_storyboard",   # 尚未有分鏡(專案層級)
    "need_images",          # 等待生成圖片候選
    "awaiting_image_pick",  # 圖片候選已生成,等待挑選
    "need_videos",          # 圖片已選,等待生成影片候選
    "awaiting_video_pick",  # 影片候選已生成,等待挑選
    "done",                 # 影片已選
]


@dataclass
class Candidate:
    """一個生成候選(圖片或影片),對應 Supabase `assets` 一列。"""

    cid: str
    url: str            # 給前端的媒體 URL(/media/...)
    kind: Literal["image", "video"]


@dataclass
class ShotState:
    shot: Shot
    stage: ShotStage = "need_images"
    route: Route = "video"              # Phase 1 分流路徑,可由使用者手動覆寫
    image_candidates: list[Candidate] = field(default_factory=list)
    selected_image: str | None = None   # candidate id
    video_candidates: list[Candidate] = field(default_factory=list)
    selected_video: str | None = None   # candidate id

    def selected_image_cand(self) -> Candidate | None:
        return next((c for c in self.image_candidates if c.cid == self.selected_image), None)

    def selected_video_cand(self) -> Candidate | None:
        return next((c for c in self.video_candidates if c.cid == self.selected_video), None)


@dataclass
class Project:
    pid: str
    prompt: str
    num_shots: int
    dynamic_ratio: float = 1.0          # Phase 1 動態分鏡比例上限
    title: str = ""
    shots: list[ShotState] = field(default_factory=list)
    characters: list[Character] = field(default_factory=list)  # Phase 2 角色庫
    costs: list[CostEntry] = field(default_factory=list)
    final_video: str | None = None      # /media URL
    saved_to_pcloud: bool = False

    def character(self, name: str) -> Character | None:
        return next((c for c in self.characters if c.name == name), None)

    def resolve_characters(self, names: list[str]) -> list[Character]:
        """把分鏡標記的角色名解析成角色物件(略過找不到的)。"""
        return [c for n in names if (c := self.character(n))]

    def as_dict(self) -> dict:
        return {
            "pid": self.pid,
            "prompt": self.prompt,
            "num_shots": self.num_shots,
            "dynamic_ratio": self.dynamic_ratio,
            "title": self.title,
            "final_video": self.final_video,
            "saved_to_pcloud": self.saved_to_pcloud,
            "total_cost_usd": round(sum(c.unit_cost_usd for c in self.costs), 4),
            "characters": [
                {
                    "name": c.name,
                    "style_tag": c.style_tag,
                    "seed": c.seed,
                    # ref_image 以專案內相對路徑保存,對外給可顯示的 /media URL
                    "ref_image": (f"/media/{self.pid}/{c.ref_image}" if c.ref_image else None),
                }
                for c in self.characters
            ],
            "shots": [
                {
                    "index": s.shot.index,
                    "description": s.shot.description,
                    "shot_type": s.shot.shot_type,
                    "needs_motion": s.shot.needs_motion,
                    "characters": s.shot.characters,
                    "route": s.route,
                    "stage": s.stage,
                    "image_candidates": [
                        {"cid": c.cid, "url": c.url} for c in s.image_candidates
                    ],
                    "selected_image": s.selected_image,
                    "video_candidates": [
                        {"cid": c.cid, "url": c.url} for c in s.video_candidates
                    ],
                    "selected_video": s.selected_video,
                }
                for s in self.shots
            ],
            "all_done": bool(self.shots) and all(s.stage == "done" for s in self.shots),
        }


class ProjectStore:
    """執行緒安全的記憶體專案儲存。"""

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}
        self._lock = threading.Lock()

    def create(self, prompt: str, num_shots: int, dynamic_ratio: float = 1.0) -> Project:
        pid = uuid.uuid4().hex[:12]
        project = Project(
            pid=pid, prompt=prompt, num_shots=num_shots, dynamic_ratio=dynamic_ratio
        )
        with self._lock:
            self._projects[pid] = project
        return project

    def get(self, pid: str) -> Project | None:
        with self._lock:
            return self._projects.get(pid)

    def list(self) -> list[Project]:
        with self._lock:
            return list(self._projects.values())
