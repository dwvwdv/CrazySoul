"""[3] Image Provider Layer 與 [5a] Video Provider Layer。

Phase 3 已抽象成統一介面(見 `base.py`):
  - `ImageProvider` / `VideoProvider` ABC + 註冊表。
  - 生圖:`image.generate_images(ImageRequest, out_paths)`,Provider 有 fal-flux / fal-sdxl。
  - 生影片:`video.generate_clips(VideoRequest, out_paths)`,Provider 有 fal-kling / fal-wan。
業務邏輯只用字串選 Provider(`cfg.image_provider` / `cfg.video_provider`),不綁死 SDK。
"""
