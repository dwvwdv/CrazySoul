"""Web Console 主線的端到端測試(dry-run)。

用 FastAPI TestClient 走完整條主線:
  登入 → 建立專案 → 產生分鏡 → 生圖候選 → 挑選 → 生影片候選 → 挑選 → 合成 → 保存。
不需要憑證或網路,只需要 ffmpeg。
"""

from __future__ import annotations

import time

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CRAZYSOUL_DRY_RUN", "1")
    monkeypatch.setenv("CRAZYSOUL_OUTPUT", str(tmp_path))
    monkeypatch.setenv("WEB_PASSWORD", "test-pw")
    monkeypatch.setenv("WEB_SECRET_KEY", "test-secret")
    # 在設好環境變數後才 import / 建立 app
    from fastapi.testclient import TestClient

    from crazysoul.web.app import create_app

    with TestClient(create_app()) as c:
        yield c


def _wait_job(client, jid, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/jobs/{jid}")
        r.raise_for_status()
        data = r.json()
        if data["status"] == "done":
            return data["result"]
        if data["status"] == "error":
            raise AssertionError(f"job error: {data['error']}")
        time.sleep(0.2)
    raise AssertionError("job timeout")


def test_auth_required(client):
    # 未登入時受保護的端點回 401
    assert client.post("/api/projects", json={"prompt": "x", "shots": 1}).status_code == 401


def test_login_wrong_password(client):
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401


def test_full_flow(client):
    # 登入
    assert client.post("/api/login", json={"password": "test-pw"}).status_code == 200
    assert client.get("/api/me").json()["authed"] is True

    # 建立專案 + 產生分鏡
    r = client.post("/api/projects", json={"prompt": "雨中的紅傘", "shots": 2})
    r.raise_for_status()
    pid = r.json()["pid"]
    _wait_job(client, r.json()["job"])

    proj = client.get(f"/api/projects/{pid}").json()
    assert len(proj["shots"]) == 2
    assert all(s["stage"] == "need_images" for s in proj["shots"])

    # 每個分鏡:生圖 → 選第一張 → 生影片 → 選第一段
    for idx in range(2):
        job = client.post(f"/api/projects/{pid}/shots/{idx}/images", json={"count": 3}).json()["job"]
        _wait_job(client, job)
        proj = client.get(f"/api/projects/{pid}").json()
        cands = proj["shots"][idx]["image_candidates"]
        assert len(cands) == 3
        # 媒體檔可透過受保護端點取得
        assert client.get(cands[0]["url"]).status_code == 200

        client.post(f"/api/projects/{pid}/shots/{idx}/select_image", json={"cid": cands[0]["cid"]})

        job = client.post(f"/api/projects/{pid}/shots/{idx}/videos", json={"count": 2}).json()["job"]
        _wait_job(client, job)
        proj = client.get(f"/api/projects/{pid}").json()
        vids = proj["shots"][idx]["video_candidates"]
        assert len(vids) == 2
        client.post(f"/api/projects/{pid}/shots/{idx}/select_video", json={"cid": vids[0]["cid"]})

    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["all_done"] is True

    # 合成最終影片
    job = client.post(f"/api/projects/{pid}/compose").json()["job"]
    _wait_job(client, job)
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["final_video"]
    assert client.get(proj["final_video"]).status_code == 200

    # 保存至 pCloud(Phase 6 前先標記)
    assert client.post(f"/api/projects/{pid}/save_pcloud").json()["saved"] is True


def test_media_path_traversal_blocked(client):
    client.post("/api/login", json={"password": "test-pw"})
    r = client.post("/api/projects", json={"prompt": "x", "shots": 1})
    pid = r.json()["pid"]
    _wait_job(client, r.json()["job"])
    # 嘗試跳出專案目錄應被擋
    resp = client.get(f"/media/{pid}/../../../etc/passwd")
    assert resp.status_code == 404
