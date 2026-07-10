"""單一密碼登入與簽章 cookie 的單元測試。"""

from __future__ import annotations

import hashlib

from crazysoul.web import auth


def test_verify_password_plaintext(monkeypatch):
    monkeypatch.setenv("WEB_PASSWORD", "secret")
    monkeypatch.delenv("WEB_PASSWORD_HASH", raising=False)
    assert auth.verify_password("secret")
    assert not auth.verify_password("wrong")


def test_verify_password_hash(monkeypatch):
    monkeypatch.delenv("WEB_PASSWORD", raising=False)
    monkeypatch.setenv("WEB_PASSWORD_HASH", hashlib.sha256(b"hunter2").hexdigest())
    assert auth.verify_password("hunter2")
    assert not auth.verify_password("nope")


def test_default_password(monkeypatch):
    monkeypatch.delenv("WEB_PASSWORD", raising=False)
    monkeypatch.delenv("WEB_PASSWORD_HASH", raising=False)
    assert auth.using_default_password() is True
    assert auth.verify_password("crazysoul")


def test_cookie_roundtrip(monkeypatch):
    monkeypatch.setenv("WEB_SECRET_KEY", "k")
    cookie = auth.issue_cookie()
    assert auth.valid_cookie(cookie)
    assert not auth.valid_cookie(None)
    assert not auth.valid_cookie("garbage")


def test_cookie_tampered(monkeypatch):
    monkeypatch.setenv("WEB_SECRET_KEY", "k")
    cookie = auth.issue_cookie()
    body, _, _sig = cookie.partition(".")
    assert not auth.valid_cookie(body + ".AAAA")


def test_cookie_expired(monkeypatch):
    monkeypatch.setenv("WEB_SECRET_KEY", "k")
    monkeypatch.setattr(auth, "_TTL_SECONDS", -10)
    assert not auth.valid_cookie(auth.issue_cookie())


def test_cookie_secret_isolation(monkeypatch):
    monkeypatch.setenv("WEB_SECRET_KEY", "k1")
    cookie = auth.issue_cookie()
    monkeypatch.setenv("WEB_SECRET_KEY", "k2")
    # 換了簽章金鑰,舊 cookie 應失效
    assert not auth.valid_cookie(cookie)
