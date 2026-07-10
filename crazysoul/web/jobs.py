"""非同步任務管理器。

對應 README「每個生成節點都是非同步任務,前端輪詢或用 WebSocket 通知完成狀態」。
Phase 4 先用前端輪詢:每個生成動作建立一個 Job,背景執行緒跑實際工作,
前端 poll GET /api/jobs/{id} 直到 done/error。
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

JobStatus = Literal["running", "done", "error"]


@dataclass
class Job:
    jid: str
    kind: str
    status: JobStatus = "running"
    error: str | None = None
    result: dict = field(default_factory=dict)


class JobManager:
    """把 blocking 工作丟到背景執行緒跑,狀態存記憶體供前端輪詢。

    用執行緒而非 asyncio task,是因為實際工作(ffmpeg subprocess、Provider SDK)
    都是 blocking 的,放執行緒最直接,也不會卡住 FastAPI 的事件迴圈。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, fn: Callable[[], dict]) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(jid=jid, kind=kind)
        with self._lock:
            self._jobs[jid] = job

        def _run() -> None:
            try:
                result = fn() or {}
                self._finish(jid, "done", result=result)
            except Exception as exc:  # noqa: BLE001 - 收進 job 狀態回報前端
                traceback.print_exc()
                self._finish(jid, "error", error=str(exc))

        threading.Thread(target=_run, daemon=True).start()
        return job

    def _finish(
        self, jid: str, status: JobStatus, error: str | None = None, result: dict | None = None
    ) -> None:
        with self._lock:
            job = self._jobs[jid]
            job.status = status
            job.error = error
            job.result = result or {}

    def get(self, jid: str) -> Job | None:
        with self._lock:
            return self._jobs.get(jid)
