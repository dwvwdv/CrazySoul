"""pCloud WebDAV upload support for Phase 6."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .config import Config


def upload_file(local_path: Path, remote_name: str, cfg: Config) -> dict:
    """Upload a file to pCloud WebDAV, or return a dry-run marker."""
    if cfg.dry_run:
        return {"uploaded": False, "dry_run": True, "remote": remote_name}
    if not (cfg.pcloud_user and cfg.pcloud_password):
        raise RuntimeError("未設定 PCLOUD_USER / PCLOUD_PASSWORD。")
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("需要 httpx 才能上傳 pCloud WebDAV。") from exc
    base = cfg.pcloud_webdav_url.rstrip("/")
    folder = "/".join(quote(p.strip("/")) for p in cfg.pcloud_folder.split("/") if p.strip("/"))
    url = f"{base}/{folder}/{quote(remote_name)}" if folder else f"{base}/{quote(remote_name)}"
    with httpx.Client(timeout=300.0, auth=(cfg.pcloud_user, cfg.pcloud_password)) as http:
        resp = http.put(url, content=local_path.read_bytes())
        resp.raise_for_status()
    return {"uploaded": True, "dry_run": False, "remote": url}
