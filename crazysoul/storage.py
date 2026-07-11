"""Phase 6 Storage: pCloud WebDAV 上傳。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx

from .config import Config
from .guardrails import retry_call


def _quote_path(path: str) -> str:
    """逐段 URL encode,保留 WebDAV 目錄斜線。"""
    return "/".join(quote(part) for part in path.split("/") if part)


def upload_webdav(local_path: Path, remote_name: str, cfg: Config) -> str:
    """把檔案透過 WebDAV PUT 上傳到 pCloud,回傳遠端路徑。"""
    if not local_path.is_file():
        raise FileNotFoundError(local_path)
    if not cfg.pcloud_webdav_url or not cfg.pcloud_username or not cfg.pcloud_password:
        raise RuntimeError("需設定 PCLOUD_WEBDAV_URL / PCLOUD_USERNAME / PCLOUD_PASSWORD")
    base = cfg.pcloud_webdav_url.rstrip("/")
    folder = cfg.pcloud_remote_dir.strip("/")
    remote_path = f"{folder}/{remote_name}" if folder else remote_name
    if folder:
        _ensure_collection(base, folder, cfg)
    url = f"{base}/{_quote_path(remote_path)}"

    def _put() -> None:
        with local_path.open("rb") as fh:
            resp = httpx.put(
                url,
                content=fh,
                auth=(cfg.pcloud_username or "", cfg.pcloud_password or ""),
                timeout=300.0,
            )
        resp.raise_for_status()

    retry_call(_put, cfg, label="pCloud WebDAV upload")
    return remote_path


def _ensure_collection(base_url: str, folder: str, cfg: Config) -> None:
    """確保 WebDAV 遠端目錄存在;已存在(405)視為成功。"""
    current = ""
    for part in [p for p in folder.split("/") if p]:
        current = f"{current}/{part}" if current else part
        url = f"{base_url}/{_quote_path(current)}"

        def _mkcol() -> None:
            resp = httpx.request(
                "MKCOL",
                url,
                auth=(cfg.pcloud_username or "", cfg.pcloud_password or ""),
                timeout=60.0,
            )
            if resp.status_code not in {201, 405}:
                resp.raise_for_status()

        retry_call(_mkcol, cfg, label="pCloud WebDAV mkdir")
