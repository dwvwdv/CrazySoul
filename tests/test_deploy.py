"""Phase 8 Docker 部署檔案測試。"""

from __future__ import annotations

from pathlib import Path


def test_docker_compose_declares_phase8_services():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "web-backend:" in compose
    assert "web-frontend:" in compose
    assert "worker:" in compose
    assert "crazysoul-output:" in compose


def test_env_example_documents_required_deploy_keys():
    env = Path(".env.example").read_text(encoding="utf-8")
    for key in ["WEB_SECRET_KEY", "FAL_KEY", "PCLOUD_WEBDAV_URL", "COST_LIMIT_USD"]:
        assert key in env
