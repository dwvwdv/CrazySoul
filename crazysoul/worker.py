"""Phase 8 worker 入口。

目前 Web Console 仍使用記憶體 JobManager 執行背景工作;這個入口讓 Docker Compose
先把 worker 容器邊界固定下來,後續接 asyncio / 外部佇列時可直接替換此處 loop。
"""

from __future__ import annotations

import signal
import time

_RUNNING = True


def _stop(_signum, _frame) -> None:
    global _RUNNING
    _RUNNING = False


def main() -> int:
    """啟動 worker placeholder loop。"""
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print("[crazysoul-worker] started; waiting for queue backend integration", flush=True)
    while _RUNNING:
        time.sleep(1.0)
    print("[crazysoul-worker] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
