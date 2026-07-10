"""管線流動的資料模型。

對應 README 的資料流:主題 → Storyboard(分鏡 JSON)→ 每個分鏡的生成產物。
用純 dataclass,不引入 ORM;之後接 Supabase 時再做 mapping。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Character:
    """角色一致性資料(Phase 2 Character DB,對應 Supabase `characters`)。

    生圖時把這些資訊帶入 Provider:`seed` 走平台原生一致性參數、
    `style_tag` 併入 prompt、`ref_image` 供支援 reference / IPAdapter 的 Provider 使用。
    """

    name: str
    ref_image: str | None = None   # 參考圖:本地路徑或可存取 URL
    seed: int | None = None        # 固定 seed,拉住同一角色的外觀一致性
    style_tag: str = ""            # 風格描述,生圖時併入 prompt

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Character":
        seed = data.get("seed")
        return Character(
            name=str(data.get("name", "")).strip(),
            ref_image=(str(data["ref_image"]) if data.get("ref_image") else None),
            seed=(int(seed) if seed not in (None, "") else None),
            style_tag=str(data.get("style_tag", "")).strip(),
        )


@dataclass
class Shot:
    """單一分鏡。對應 README「Storyboard Generator」的輸出結構。"""

    index: int
    description: str            # 畫面描述(送給生圖 Provider 的 prompt)
    shot_type: str = "medium"  # 鏡頭類型:wide / medium / close 等
    needs_motion: bool = True  # 是否標記為「需要動態」(Phase 1 Routing 用)
    duration: float = 5.0      # 預估秒數
    motion_hint: str = ""      # 給影片 Provider 的運鏡提示
    characters: list[str] = field(default_factory=list)  # 出場角色名(Phase 2,生圖自動帶入)

    @staticmethod
    def from_dict(data: dict[str, Any], index: int) -> "Shot":
        raw_chars = data.get("characters") or []
        return Shot(
            index=index,
            description=str(data.get("description", "")).strip(),
            shot_type=str(data.get("shot_type", "medium")),
            needs_motion=bool(data.get("needs_motion", True)),
            duration=float(data.get("duration", 5.0)),
            motion_hint=str(data.get("motion_hint", "")),
            characters=[str(c).strip() for c in raw_chars if str(c).strip()],
        )


@dataclass
class Storyboard:
    """一整支影片的分鏡腳本。"""

    prompt: str
    title: str
    shots: list[Shot] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "title": self.title,
            "shots": [asdict(s) for s in self.shots],
        }


@dataclass
class CostEntry:
    """單次 Provider 呼叫的成本紀錄(對應 Supabase `cost_log`)。"""

    stage: str          # storyboard / image / video / compose
    provider: str
    unit_cost_usd: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShotResult:
    """單一分鏡跑完後的產物路徑。"""

    shot: Shot
    image_path: str
    clip_path: str


@dataclass
class RunResult:
    """一次完整 run 的結果。"""

    run_dir: str
    storyboard: Storyboard
    shot_results: list[ShotResult]
    final_video: str
    costs: list[CostEntry]

    @property
    def total_cost_usd(self) -> float:
        return round(sum(c.unit_cost_usd for c in self.costs), 4)
