"""FastAPI 應用:Web Console 的 API 與內嵌前端。

前端(static/)由後端直接提供,不需要另外的 build 工具鏈。
每個生成節點都是非同步任務(見 jobs.py),前端輪詢 /api/jobs/{id}。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import Config
from . import auth, service
from .jobs import JobManager
from .store import ProjectStore

_STATIC = Path(__file__).parent / "static"


# 請求 body 模型放在模組層級——搭配 `from __future__ import annotations`,
# FastAPI 需要能在模組 globals 解析型別註解,定義在函式內會被誤判成 query 參數。
class LoginBody(BaseModel):
    password: str


class CreateProjectBody(BaseModel):
    prompt: str
    shots: int = 3


class CountBody(BaseModel):
    count: int = 4


class PickBody(BaseModel):
    cid: str


def make_config() -> Config:
    cfg = Config.load()
    flag = os.environ.get("CRAZYSOUL_DRY_RUN", "").strip().lower()
    cfg.dry_run = flag in {"1", "true", "yes", "on"}
    out = os.environ.get("CRAZYSOUL_OUTPUT")
    if out:
        cfg.output_root = Path(out)
    return cfg


def create_app() -> FastAPI:
    app = FastAPI(title="CrazySoul Web Console", version="0.1.0")
    cfg = make_config()
    store = ProjectStore()
    jobs = JobManager()

    # ---- 身分驗證 ----
    def require_auth(cs_session: str | None = Cookie(default=None)) -> None:
        if not auth.valid_cookie(cs_session):
            raise HTTPException(status_code=401, detail="未登入")

    @app.post("/api/login")
    def login(body: LoginBody, response: Response):
        if not auth.verify_password(body.password):
            raise HTTPException(status_code=401, detail="密碼錯誤")
        response.set_cookie(
            auth.COOKIE_NAME,
            auth.issue_cookie(),
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 3600,
        )
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(auth.COOKIE_NAME)
        return {"ok": True}

    @app.get("/api/me")
    def me(cs_session: str | None = Cookie(default=None)):
        return {
            "authed": auth.valid_cookie(cs_session),
            "dry_run": cfg.dry_run,
            "default_password": auth.using_default_password(),
        }

    # ---- 專案 / 主線 ----
    @app.post("/api/projects", dependencies=[Depends(require_auth)])
    def create_project(body: CreateProjectBody):
        project = store.create(body.prompt.strip(), max(1, min(body.shots, 8)))
        job = jobs.submit("storyboard", lambda: service.run_storyboard(cfg, project))
        return {"pid": project.pid, "job": job.jid}

    @app.get("/api/projects/{pid}", dependencies=[Depends(require_auth)])
    def get_project(pid: str):
        project = store.get(pid)
        if not project:
            raise HTTPException(status_code=404, detail="找不到專案")
        return project.as_dict()

    def _project(pid: str):
        project = store.get(pid)
        if not project:
            raise HTTPException(status_code=404, detail="找不到專案")
        return project

    @app.post("/api/projects/{pid}/shots/{idx}/images", dependencies=[Depends(require_auth)])
    def gen_images(pid: str, idx: int, body: CountBody):
        project = _project(pid)
        n = max(1, min(body.count, 8))
        job = jobs.submit(
            "images", lambda: service.run_image_candidates(cfg, project, idx, n)
        )
        return {"job": job.jid}

    @app.post("/api/projects/{pid}/shots/{idx}/select_image", dependencies=[Depends(require_auth)])
    def pick_image(pid: str, idx: int, body: PickBody):
        try:
            return service.select_image(_project(pid), idx, body.cid)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/projects/{pid}/shots/{idx}/videos", dependencies=[Depends(require_auth)])
    def gen_videos(pid: str, idx: int, body: CountBody):
        project = _project(pid)
        n = max(1, min(body.count, 6))
        job = jobs.submit(
            "videos", lambda: service.run_video_candidates(cfg, project, idx, n)
        )
        return {"job": job.jid}

    @app.post("/api/projects/{pid}/shots/{idx}/select_video", dependencies=[Depends(require_auth)])
    def pick_video(pid: str, idx: int, body: PickBody):
        try:
            return service.select_video(_project(pid), idx, body.cid)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/projects/{pid}/compose", dependencies=[Depends(require_auth)])
    def compose(pid: str):
        project = _project(pid)
        job = jobs.submit("compose", lambda: service.run_compose(cfg, project))
        return {"job": job.jid}

    @app.post("/api/projects/{pid}/save_pcloud", dependencies=[Depends(require_auth)])
    def save_pcloud(pid: str):
        try:
            return service.save_to_pcloud(_project(pid))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/jobs/{jid}", dependencies=[Depends(require_auth)])
    def job_status(jid: str):
        job = jobs.get(jid)
        if not job:
            raise HTTPException(status_code=404, detail="找不到任務")
        return {"status": job.status, "error": job.error, "result": job.result}

    # ---- 媒體檔(受登入保護,防目錄穿越)----
    @app.get("/media/{pid}/{path:path}", dependencies=[Depends(require_auth)])
    def media(pid: str, path: str):
        base = (cfg.output_root / "web" / pid).resolve()
        target = (base / path).resolve()
        if not target.is_file() or base not in target.parents and target.parent != base:
            raise HTTPException(status_code=404, detail="找不到檔案")
        return FileResponse(target)

    # ---- 前端 ----
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.get("/")
    def index():
        return FileResponse(_STATIC / "index.html")

    @app.exception_handler(HTTPException)
    async def _http_exc(_request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()
