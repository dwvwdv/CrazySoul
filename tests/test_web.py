"""Web Console 主線的端到端測試(dry-run)。

用 FastAPI TestClient 走完整條主線:
  登入 → 建立專案 → 產生分鏡 → 生圖候選 → 挑選 → 生影片候選 → 挑選 → 合成 → 保存。
不需要憑證或網路,只需要 ffmpeg。
"""

from __future__ import annotations

import time

import pytest

from crazysoul.ffmpeg import run as ffmpeg_run


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


def _make_test_music(path):
    ffmpeg_run([
        "-f", "lavfi",
        "-i", "sine=frequency=330:sample_rate=44100:duration=2",
        "-c:a", "pcm_s16le",
        str(path),
    ])
    return path


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


def test_full_flow(client, tmp_path):
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
        if idx == 0:
            resp = client.post(f"/api/projects/{pid}/shots/{idx}/extend", json={"seconds": 5})
            resp.raise_for_status()
            assert resp.json()["extended"] is True

    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["all_done"] is True

    # 上傳背景音樂後合成最終影片
    music = _make_test_music(tmp_path / "music.wav")
    with music.open("rb") as fh:
        resp = client.post(
            f"/api/projects/{pid}/background_music",
            files={"file": ("music.wav", fh, "audio/wav")},
        )
    resp.raise_for_status()
    assert resp.json()["background_music"].endswith("/audio/background_music.wav")
    resp = client.post(f"/api/projects/{pid}/subtitles", json={"text": "第一句字幕。第二句字幕。"})
    resp.raise_for_status()
    assert resp.json()["subtitle_text"].startswith("第一句")

    job = client.post(f"/api/projects/{pid}/compose").json()["job"]
    _wait_job(client, job)
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["background_music"]
    assert proj["subtitle_text"]
    assert proj["subtitles"]
    assert proj["final_video"]
    assert client.get(proj["final_video"]).status_code == 200

    costs = client.get(f"/api/projects/{pid}/costs").json()
    assert "estimated_with_retry_usd" in costs
    assert "video" in costs["by_stage"]

    # 保存至 pCloud(dry-run 仍標記佔位,live 走 WebDAV)
    assert client.post(f"/api/projects/{pid}/save_pcloud").json()["saved"] is True


def test_routing_default_and_override(client):
    client.post("/api/login", json={"password": "test-pw"})
    # dynamic_ratio=0 → 全部分鏡預設走靜態 motion
    r = client.post("/api/projects", json={"prompt": "分流測試", "shots": 3, "dynamic_ratio": 0})
    pid = r.json()["pid"]
    _wait_job(client, r.json()["job"])

    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["dynamic_ratio"] == 0
    assert all(s["route"] == "motion" for s in proj["shots"])
    # 每個分鏡都帶出 needs_motion 供前端顯示
    assert all("needs_motion" in s for s in proj["shots"])

    # 手動覆寫第一個分鏡為動態 video
    assert client.post(
        f"/api/projects/{pid}/shots/0/route", json={"route": "video"}
    ).json()["route"] == "video"
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["shots"][0]["route"] == "video"

    # 未知路徑值應被擋
    assert client.post(
        f"/api/projects/{pid}/shots/0/route", json={"route": "bogus"}
    ).status_code == 400


def test_routing_full_ratio_follows_needs_motion(client):
    client.post("/api/login", json={"password": "test-pw"})
    # dynamic_ratio=1 → 依 needs_motion 分流(dry-run 交錯:0=動態,1=靜態)
    r = client.post("/api/projects", json={"prompt": "x", "shots": 2, "dynamic_ratio": 1})
    pid = r.json()["pid"]
    _wait_job(client, r.json()["job"])
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["shots"][0]["route"] == "video"
    assert proj["shots"][1]["route"] == "motion"


def test_character_crud_and_assignment(client):
    client.post("/api/login", json={"password": "test-pw"})
    r = client.post("/api/projects", json={"prompt": "貓的故事", "shots": 2})
    pid = r.json()["pid"]
    _wait_job(client, r.json()["job"])

    # 新增角色(含參考圖上傳)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32  # 假 PNG bytes,dry-run 不會真的解碼
    resp = client.post(
        f"/api/projects/{pid}/characters",
        data={"name": "小黑貓", "style_tag": "黑色短毛,綠眼", "seed": "1234"},
        files={"file": ("ref.png", png, "image/png")},
    )
    assert resp.status_code == 200

    # 再新增一個無參考圖的角色
    assert client.post(
        f"/api/projects/{pid}/characters", data={"name": "小白", "style_tag": "白貓"}
    ).status_code == 200

    proj = client.get(f"/api/projects/{pid}").json()
    names = {c["name"] for c in proj["characters"]}
    assert names == {"小黑貓", "小白"}
    black = next(c for c in proj["characters"] if c["name"] == "小黑貓")
    assert black["seed"] == 1234
    assert black["ref_image"].startswith(f"/media/{pid}/characters/")
    # 參考圖可透過受保護端點取得
    assert client.get(black["ref_image"]).status_code == 200

    # 標記分鏡 0 出場角色
    assert client.post(
        f"/api/projects/{pid}/shots/0/characters", json={"names": ["小黑貓", "不存在"]}
    ).json()["characters"] == ["小黑貓"]  # 不存在的角色被過濾

    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["shots"][0]["characters"] == ["小黑貓"]

    # 生圖:帶入角色後仍能產出候選
    job = client.post(f"/api/projects/{pid}/shots/0/images", json={"count": 2}).json()["job"]
    _wait_job(client, job)
    proj = client.get(f"/api/projects/{pid}").json()
    assert len(proj["shots"][0]["image_candidates"]) == 2


def test_add_character_requires_name(client):
    client.post("/api/login", json={"password": "test-pw"})
    r = client.post("/api/projects", json={"prompt": "x", "shots": 1})
    pid = r.json()["pid"]
    _wait_job(client, r.json()["job"])
    # 空名稱應被擋
    assert client.post(
        f"/api/projects/{pid}/characters", data={"name": "   "}
    ).status_code == 400
    # 非整數 seed 應被擋
    assert client.post(
        f"/api/projects/{pid}/characters", data={"name": "a", "seed": "abc"}
    ).status_code == 400


def test_media_path_traversal_blocked(client):
    client.post("/api/login", json={"password": "test-pw"})
    r = client.post("/api/projects", json={"prompt": "x", "shots": 1})
    pid = r.json()["pid"]
    _wait_job(client, r.json()["job"])
    # 嘗試跳出專案目錄應被擋
    resp = client.get(f"/media/{pid}/../../../etc/passwd")
    assert resp.status_code == 404
