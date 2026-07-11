"""Phase 8 Docker 部署檔案測試。"""

from __future__ import annotations

from pathlib import Path


def test_docker_compose_declares_phase8_services():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "web-backend:" in compose
    assert "web-frontend:" in compose
    assert "worker:" in compose
    assert "crazysoul-output:" in compose
    assert "crazysoul.worker" in compose


def test_dockerignore_excludes_secrets_and_artifacts():
    # review P1:.env 不可被 COPY . . 烤進 image layer
    lines = Path(".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lines
    assert "output/" in lines
    assert ".git" in lines


def test_compose_web_services_bind_all_interfaces():
    # review P2:容器內預設 127.0.0.1 只綁 loopback,對外服務必須綁 0.0.0.0
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("CRAZYSOUL_WEB_HOST: 0.0.0.0") == 2


def test_env_example_documents_required_deploy_keys():
    env = Path(".env.example").read_text(encoding="utf-8")
    for key in ["WEB_SECRET_KEY", "FAL_KEY", "TTS_MODEL", "PCLOUD_WEBDAV_URL", "COST_LIMIT_USD"]:
        assert key in env
