"""Phase 3 Provider 抽象層與 Phase 2 角色一致性的單元測試(dry-run)。"""

from __future__ import annotations

import pytest

from crazysoul.config import Config
from crazysoul.models import Character, CostEntry, Shot
from crazysoul.providers.base import (
    ImageRequest,
    VideoRequest,
    get_image_provider,
    image_provider_names,
    video_provider_names,
)
from crazysoul.providers.image import generate_image, generate_images
from crazysoul.providers.video import extend_clip_with_provider, generate_clips


# ---- 註冊表 ----
def test_registry_has_two_providers_each():
    assert {"fal-flux", "fal-sdxl"} <= set(image_provider_names())
    assert {"fal-kling", "fal-wan"} <= set(video_provider_names())


def test_unknown_provider_raises():
    with pytest.raises(NotImplementedError):
        get_image_provider("does-not-exist")


# ---- ImageRequest 角色一致性 ----
def test_effective_prompt_merges_style_tags():
    req = ImageRequest(
        prompt="一隻貓",
        characters=[Character(name="小黑", style_tag="黑貓,綠眼"), Character(name="小白")],
    )
    assert req.effective_prompt() == "一隻貓,黑貓,綠眼"


def test_base_seed_prefers_first_with_seed():
    req = ImageRequest(
        prompt="x",
        characters=[Character(name="a"), Character(name="b", seed=42), Character(name="c", seed=7)],
    )
    assert req.base_seed() == 42


def test_reference_images_collected():
    req = ImageRequest(
        prompt="x",
        characters=[Character(name="a", ref_image="a.png"), Character(name="b")],
    )
    assert req.reference_images() == ["a.png"]


# ---- 原生批量 count=n ----
def test_generate_images_native_batch(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    costs: list[CostEntry] = []
    req = ImageRequest(prompt="貓", shot_index=0)
    outs = [tmp_path / f"c{k}.png" for k in range(3)]
    result = generate_images(req, outs, cfg, costs)
    assert len(result) == 3 and all(p.exists() and p.stat().st_size > 0 for p in outs)
    # 每個候選都有一筆 image 成本
    assert sum(1 for c in costs if c.stage == "image") == 3
    # 不同候選的佔位圖內容應不同(seed 拉開差異)
    assert outs[0].read_bytes() != outs[1].read_bytes()


# ---- 切換第二家 Provider ----
def test_switch_to_sdxl_provider(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path, image_provider="fal-sdxl")
    costs: list[CostEntry] = []
    generate_image(Shot(index=0, description="d"), tmp_path / "a.png", cfg, costs)
    assert costs[-1].provider == "dry-run/fal-sdxl"


def test_switch_to_wan_provider(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path, video_provider="fal-wan")
    costs: list[CostEntry] = []
    # 先要有一張圖當輸入
    from crazysoul import ffmpeg

    img = tmp_path / "in.png"
    ffmpeg.make_placeholder_image(img, label="x", seed=1)
    req = VideoRequest(image_path=img, duration=2.0, shot_index=0)
    generate_clips(req, [tmp_path / "v0.mp4"], cfg, costs)
    assert costs[-1].provider == "dry-run/fal-wan"


# ---- 角色 seed 帶入影響佔位差異 ----
def test_character_seed_changes_placeholder(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    costs: list[CostEntry] = []
    shot = Shot(index=0, description="貓")
    plain = tmp_path / "plain.png"
    withchar = tmp_path / "withchar.png"
    generate_image(shot, plain, cfg, costs)
    generate_image(shot, withchar, cfg, costs, characters=[Character(name="小黑", seed=200)])
    # 帶了角色 seed 後,佔位圖的色相不同 → 內容不同
    assert plain.read_bytes() != withchar.read_bytes()


def test_video_provider_extend_dry_run(tmp_path):
    cfg = Config(dry_run=True, output_root=tmp_path)
    costs: list[CostEntry] = []
    from crazysoul import ffmpeg

    img = tmp_path / "in.png"
    src = tmp_path / "src.mp4"
    out = tmp_path / "extended.mp4"
    ffmpeg.make_placeholder_image(img, label="x", seed=1)
    ffmpeg.image_to_motion_clip(img, src, 1.0)
    extend_clip_with_provider(src, out, cfg, costs, extend_seconds=5)
    assert out.exists() and out.stat().st_size > 0
    assert costs[-1].stage == "extend"
