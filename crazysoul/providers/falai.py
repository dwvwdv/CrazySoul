"""fal.ai 共用 HTTP 呼叫。

Flux(生圖)與 Kling(生影片)Phase 0 都經由 fal.ai,共用同一套
提交 / 輪詢 / 下載邏輯。實際模型 endpoint 由呼叫端指定。
"""

from __future__ import annotations

import time
from pathlib import Path

FAL_QUEUE = "https://queue.fal.run"


def _client(fal_key: str):
    try:
        import httpx
    except ImportError as exc:  # noqa: TRY003
        raise RuntimeError(
            "需要 httpx 才能呼叫 fal.ai:pip install httpx(或改用 --dry-run)。"
        ) from exc
    return httpx.Client(
        timeout=120.0,
        headers={"Authorization": f"Key {fal_key}"},
    )


def run_model(fal_key: str, endpoint: str, payload: dict, poll_seconds: float = 3.0) -> dict:
    """提交一個 fal.ai 任務並輪詢到完成,回傳結果 JSON。

    endpoint 例:'fal-ai/flux/dev'、'fal-ai/kling-video/v1/standard/image-to-video'。
    """
    with _client(fal_key) as http:
        submit = http.post(f"{FAL_QUEUE}/{endpoint}", json=payload)
        submit.raise_for_status()
        job = submit.json()
        status_url = job["status_url"]
        response_url = job["response_url"]

        while True:
            st = http.get(status_url)
            st.raise_for_status()
            status = st.json().get("status")
            if status == "COMPLETED":
                break
            if status in {"FAILED", "CANCELLED"}:
                raise RuntimeError(f"fal.ai 任務失敗:{status} — {st.text}")
            time.sleep(poll_seconds)

        result = http.get(response_url)
        result.raise_for_status()
        return result.json()


def download(url: str, out_path: Path, fal_key: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _client(fal_key) as http:
        resp = http.get(url)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
