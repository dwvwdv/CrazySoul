"""[Phase 3] Provider 抽象層。

把生圖 / 生影片包成統一介面,業務邏輯只認 `ImageProvider` / `VideoProvider`,
不綁死任何一家 SDK(README 慣例)。加一家新 Provider 只需實作介面並註冊,
不動 pipeline / web。

統一介面:
  - image.generate(ImageRequest, out_paths)  → 一次產出 len(out_paths) 張(count=n 原生批量)
  - video.generate(VideoRequest, out_paths)  → 一次產出 len(out_paths) 段候選

角色一致性(Phase 2):`ImageRequest.characters` 帶入 seed(平台原生一致性參數)、
style_tag(併入 prompt)、ref_image(供支援 reference / IPAdapter 的 Provider)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config
from ..models import Character, CostEntry


@dataclass
class ImageRequest:
    """一次生圖請求(對應一個分鏡的 n 張候選)。"""

    prompt: str
    shot_index: int = 0
    characters: list[Character] = field(default_factory=list)

    def effective_prompt(self) -> str:
        """把角色 style_tag 併入 prompt,強化跨分鏡一致性。"""
        tags = [c.style_tag for c in self.characters if c.style_tag]
        if not tags:
            return self.prompt
        return f"{self.prompt},{','.join(tags)}"

    def base_seed(self) -> int | None:
        """有角色且設了 seed 時,用它當一致性基準;否則回 None(讓 Provider 自由)。"""
        return next((c.seed for c in self.characters if c.seed is not None), None)

    def reference_images(self) -> list[str]:
        """出場角色的參考圖(本地路徑或 URL),供支援 reference 的 Provider 使用。"""
        return [c.ref_image for c in self.characters if c.ref_image]


@dataclass
class VideoRequest:
    """一次生影片請求(image-to-video)。"""

    image_path: Path
    duration: float
    motion_hint: str = ""
    shot_index: int = 0


class ImageProvider(ABC):
    """生圖 Provider 統一介面。"""

    name: str = ""
    unit_cost_usd: float = 0.0

    @abstractmethod
    def generate(
        self,
        req: ImageRequest,
        out_paths: list[Path],
        cfg: Config,
        costs: list[CostEntry],
        start: int = 0,
    ) -> list[Path]:
        """產出 len(out_paths) 張圖到指定路徑,回傳實際產出的路徑清單。

        `start` 是候選起始序號:用來在「重生」時位移 seed / 佔位差異,
        讓新一批候選不與舊的重覆。
        """


class VideoProvider(ABC):
    """生影片 Provider 統一介面。"""

    name: str = ""
    unit_cost_usd: float = 0.0

    @abstractmethod
    def generate(
        self,
        req: VideoRequest,
        out_paths: list[Path],
        cfg: Config,
        costs: list[CostEntry],
        start: int = 0,
    ) -> list[Path]:
        """產出 len(out_paths) 段影片到指定路徑,回傳實際產出的路徑清單。"""

    def extend(
        self,
        src_path: Path,
        out_path: Path,
        cfg: Config,
        costs: list[CostEntry],
        *,
        extend_seconds: float = 5.0,
    ) -> Path:
        """延伸既有影片片段;Provider 可覆寫 live API,dry-run 使用本地 FFmpeg。"""
        from ..ffmpeg import extend_clip

        if not cfg.dry_run:
            raise NotImplementedError(f"{self.name} 尚未實作 live extend()")
        extend_clip(src_path, out_path, extend_seconds=extend_seconds)
        costs.append(CostEntry("extend", f"dry-run/{self.name}", 0.0, f"+{extend_seconds:.0f}s"))
        return out_path


# ---- 註冊表:字串 → Provider 實例 ----
_IMAGE_PROVIDERS: dict[str, ImageProvider] = {}
_VIDEO_PROVIDERS: dict[str, VideoProvider] = {}


def register_image_provider(cls: type[ImageProvider]) -> type[ImageProvider]:
    """類別裝飾器:實例化並註冊(以 `name` 為鍵),回傳原類別。"""
    _IMAGE_PROVIDERS[cls.name] = cls()
    return cls


def register_video_provider(cls: type[VideoProvider]) -> type[VideoProvider]:
    """類別裝飾器:實例化並註冊(以 `name` 為鍵),回傳原類別。"""
    _VIDEO_PROVIDERS[cls.name] = cls()
    return cls


def get_image_provider(name: str) -> ImageProvider:
    try:
        return _IMAGE_PROVIDERS[name]
    except KeyError:
        raise NotImplementedError(
            f"未知的生圖 Provider {name!r}。可用:{sorted(_IMAGE_PROVIDERS)}"
        ) from None


def get_video_provider(name: str) -> VideoProvider:
    try:
        return _VIDEO_PROVIDERS[name]
    except KeyError:
        raise NotImplementedError(
            f"未知的生影片 Provider {name!r}。可用:{sorted(_VIDEO_PROVIDERS)}"
        ) from None


def image_provider_names() -> list[str]:
    return sorted(_IMAGE_PROVIDERS)


def video_provider_names() -> list[str]:
    return sorted(_VIDEO_PROVIDERS)
