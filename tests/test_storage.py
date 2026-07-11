"""Phase 6 pCloud WebDAV storage tests."""

from __future__ import annotations

from pathlib import Path

import httpx

from crazysoul.config import Config
from crazysoul.storage import upload_webdav


class _Resp:
    def __init__(self, status_code=201):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 405:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


def test_upload_webdav_creates_remote_dir_and_puts_file(tmp_path, monkeypatch):
    src = tmp_path / "final.mp4"
    src.write_bytes(b"video")
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return _Resp(201)

    def fake_put(url, **kwargs):
        calls.append(("PUT", url))
        assert kwargs["content"].read() == b"video"
        return _Resp(200)

    monkeypatch.setattr(httpx, "request", fake_request)
    monkeypatch.setattr(httpx, "put", fake_put)
    cfg = Config(
        pcloud_webdav_url="https://webdav.example",
        pcloud_username="u",
        pcloud_password="p",
        pcloud_remote_dir="Crazy Soul/Exports",
        retry_backoff_seconds=0,
    )
    remote = upload_webdav(src, "測試 final.mp4", cfg)
    assert remote == "Crazy Soul/Exports/測試 final.mp4"
    assert calls[0] == ("MKCOL", "https://webdav.example/Crazy%20Soul")
    assert calls[1] == ("MKCOL", "https://webdav.example/Crazy%20Soul/Exports")
    assert calls[-1] == ("PUT", "https://webdav.example/Crazy%20Soul/Exports/%E6%B8%AC%E8%A9%A6%20final.mp4")
