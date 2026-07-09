"""單一密碼身分驗證。

README:單一密碼登入,環境變數存密碼 hash,登入後發 session cookie,
不做帳號系統、不做角色權限。

這裡用 HMAC 簽章的 cookie,不需要伺服器端 session 儲存:
cookie 值 = base64(payload).base64(HMAC(secret, payload)),重啟後(若 secret 固定)仍有效。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

_COOKIE_NAME = "cs_session"
_TTL_SECONDS = 7 * 24 * 3600  # 7 天


def _password_hash() -> str:
    """回傳設定的密碼 sha256 hex。

    優先讀 WEB_PASSWORD_HASH(sha256 hex);否則把 WEB_PASSWORD 明文 hash;
    兩者皆無則用開發預設密碼(會在啟動時警告)。
    """
    h = os.environ.get("WEB_PASSWORD_HASH")
    if h:
        return h.strip().lower()
    plain = os.environ.get("WEB_PASSWORD")
    if not plain:
        plain = "crazysoul"  # 開發預設,正式部署務必覆蓋
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def using_default_password() -> bool:
    return not (os.environ.get("WEB_PASSWORD_HASH") or os.environ.get("WEB_PASSWORD"))


def _secret() -> bytes:
    """cookie 簽章金鑰。設 WEB_SECRET_KEY 可跨重啟保留 session;否則每次啟動隨機。"""
    key = os.environ.get("WEB_SECRET_KEY")
    if key:
        return key.encode("utf-8")
    # 程序層級固定的隨機金鑰(重啟後現有 session 失效,單人工具可接受)
    global _RUNTIME_SECRET
    try:
        return _RUNTIME_SECRET
    except NameError:
        _RUNTIME_SECRET = secrets.token_bytes(32)
        return _RUNTIME_SECRET


def verify_password(password: str) -> bool:
    given = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(given, _password_hash())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_cookie() -> str:
    payload = f"ok:{int(time.time()) + _TTL_SECONDS}".encode("utf-8")
    sig = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(sig)}"


def valid_cookie(value: str | None) -> bool:
    if not value or "." not in value:
        return False
    body, _, sig = value.partition(".")
    try:
        payload = _b64d(body)
        expected = hmac.new(_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            return False
        _, _, exp = payload.decode("utf-8").partition(":")
        return int(exp) > int(time.time())
    except Exception:  # noqa: BLE001
        return False


COOKIE_NAME = _COOKIE_NAME
