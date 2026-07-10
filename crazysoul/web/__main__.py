"""啟動 Web Console:python -m crazysoul.web

環境變數:
  WEB_PASSWORD / WEB_PASSWORD_HASH  登入密碼(未設定則用開發預設 crazysoul)
  WEB_SECRET_KEY                    cookie 簽章金鑰(未設定則每次啟動隨機)
  CRAZYSOUL_DRY_RUN=1               離線模式,用 FFmpeg 佔位素材,不呼叫付費 API
  CRAZYSOUL_WEB_HOST / _PORT        綁定位址(預設 127.0.0.1:8000)
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("CRAZYSOUL_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("CRAZYSOUL_WEB_PORT", "8000"))
    uvicorn.run("crazysoul.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
