"""JobManager、成本護欄、分鏡建構、Provider 的單元測試。"""

from __future__ import annotations

import time

import pytest

from crazysoul.config import Config
from crazysoul.models import CostEntry, Shot
from crazysoul.pipeline import _check_budget
from crazysoul.providers.image import generate_image
from crazysoul.storyboard import _build, generate_storyboard
from crazysoul.web.jobs import JobManager


# ---- JobManager ----
def _wait(jm: JobManager, jid: str):
    for _ in range(100):
        job = jm.get(jid)
        if job and job.status != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job timeout")


def test_job_success():
    jm = JobManager()
    job = jm.submit("t", lambda: {"v": 42})
    done = _wait(jm, job.jid)
    assert done.status == "done"
    assert done.result == {"v": 42}


def test_job_error():
    jm = JobManager()

    def boom() -> dict:
        raise RuntimeError("爆炸了")

    done = _wait(jm, jm.submit("t", boom).jid)
    assert done.status == "error"
    assert "爆炸了" in (done.error or "")


def test_job_missing():
    assert JobManager().get("nope") is None


# ---- 成本護欄 ----
def test_budget_ok():
    cfg = Config(cost_limit_usd=1.0, cost_retry_factor=1.0)
    _check_budget(cfg, [CostEntry("image", "p", 0.3)])  # 不應拋錯


def test_budget_exceeded():
    cfg = Config(cost_limit_usd=1.0, cost_retry_factor=1.4)
    # 0.8 × 1.4 = 1.12 > 1.0
    with pytest.raises(RuntimeError):
        _check_budget(cfg, [CostEntry("video", "p", 0.8)])


def test_budget_disabled_when_zero():
    cfg = Config(cost_limit_usd=0.0, cost_retry_factor=1.4)
    _check_budget(cfg, [CostEntry("video", "p", 999.0)])  # 上限 0 = 不限制


# ---- 分鏡建構 ----
def test_dry_run_storyboard_shape():
    costs: list[CostEntry] = []
    sb = generate_storyboard("主題", Config(dry_run=True), costs, num_shots=4)
    assert len(sb.shots) == 4
    assert [s.index for s in sb.shots] == [0, 1, 2, 3]
    assert costs and costs[0].stage == "storyboard"


def test_build_from_llm_dict():
    data = {
        "title": "T",
        "shots": [
            {
                "description": "a", "shot_type": "close",
                "needs_motion": False, "duration": 3, "motion_hint": "pan",
            }
        ],
    }
    sb = _build("p", data)
    assert sb.title == "T"
    assert sb.shots[0].needs_motion is False
    assert sb.shots[0].motion_hint == "pan"
    assert sb.shots[0].shot_type == "close"


# ---- Provider(dry-run)----
def test_image_dry_run_creates_file(tmp_path):
    costs: list[CostEntry] = []
    out = generate_image(
        Shot(index=0, description="d"), tmp_path / "a.png", Config(dry_run=True), costs, variant=1
    )
    assert out.exists() and out.stat().st_size > 0
    assert costs[0].stage == "image"
