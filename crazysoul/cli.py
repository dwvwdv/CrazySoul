"""Phase 0 CLI 入口。

用法:
    python -m crazysoul.cli --prompt "深夜便利商店的貓" --dry-run
    python -m crazysoul.cli --prompt "..." --shots 4        # 需設定憑證
"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crazysoul",
        description="CrazySoul Phase 0 — 打通單一路徑的短影音生成管線。",
    )
    p.add_argument("--prompt", "-p", required=True, help="主題/大綱文字。")
    p.add_argument("--shots", "-n", type=int, default=3, help="分鏡數量(預設 3)。")
    p.add_argument(
        "--dynamic-ratio",
        type=float,
        default=None,
        help="動態分鏡比例上限 [0,1]:最多這個比例的分鏡走付費 Video Provider,"
        "其餘退回 Motion Engine(FFmpeg)。省略則用環境變數 DYNAMIC_RATIO(預設 1.0)。",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="離線模式:不呼叫任何付費 API,用 FFmpeg 佔位素材驗證資料流。",
    )
    p.add_argument("--output", "-o", default="output", help="產物根目錄(預設 output/)。")
    p.add_argument("--voiceover", default=None, help="Phase 5:要合成到影片中的 TTS 旁白文字。")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg = Config.load()
    cfg.dry_run = args.dry_run
    if args.dynamic_ratio is not None:
        cfg.dynamic_ratio = min(max(args.dynamic_ratio, 0.0), 1.0)
    from pathlib import Path

    cfg.output_root = Path(args.output)

    try:
        run_pipeline(args.prompt, cfg, num_shots=args.shots, voiceover_text=args.voiceover)
    except Exception as exc:  # noqa: BLE001 - CLI 邊界,給使用者清楚訊息
        print(f"[crazysoul] 錯誤:{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
