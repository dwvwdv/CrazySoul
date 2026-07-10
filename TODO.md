# TODO — CrazySoul 開發待辦

> 這份清單是開發的**單一事實來源**。
> 每次開發**前**先讀這裡,從「🔜 下一步」挑最靠前、未勾選的項目做;
> 開發**完成後**回來勾選,並補上新發現的子任務 / 技術債。
> 順序原則:照 `README.md`「實作階段建議」逐 Phase 做,不跳著做
> (Phase 4 Web Console 已依 README 建議提前完成)。跨階段基礎可穿插。

---

## ✅ 已完成
- [x] **Phase 0** — 打通單一路徑(LLM 分鏡 → 生圖 → 生影片 → FFmpeg 串接),CLI + dry-run
- [x] **Phase 4** — Web Console 最小可用版(登入 → 批量生成 → 縮圖牆挑選 → 合成 → 保存佔位)
- [x] 縮圖牆批量候選(Phase 3 的 `count=n` 雛形,用 variant 產生差異)
- [x] lazyrhythm-design 基礎風格(Nord × Brutalism)
- [x] CI(GitHub Actions,Python 3.11 / 3.12)+ 測試 29 項

---

## 🔜 下一步(建議順序)

### Phase 1 — Routing Decision(降成本核心,優先)
- [ ] 依 storyboard 的 `needs_motion` 分流:需要動態 → Video Provider;靜態即可 → Motion Engine(FFmpeg zoompan,`ffmpeg.image_to_motion_clip` 已有)
- [ ] 「動態分鏡比例」做成可調參數(config + Web UI)
- [ ] Web Console 每個分鏡顯示走哪條路徑,並可手動覆寫
- [ ] 測試:分流邏輯單元測試 + 混合路徑合成端到端

### Phase 2 — Character DB(角色一致性)
- [ ] `characters` 資料結構(名稱、參考圖、seed、風格 tag)
- [ ] Web Console:上傳角色參考圖
- [ ] 生圖時帶入參考圖(reference / IPAdapter)或平台原生一致性參數
- [ ] 分鏡可標記出場角色,生圖自動帶入

### Phase 3 — Provider 抽象層
- [ ] 把 image/video 包成統一介面 `image.generate(prompt, character_ref, count=n)` / `video.generate(image, duration, motion_hint, count=n)`
- [ ] 新增第二家 provider(image: SDXL/GPT-Image;video: Wan)驗證抽象成立
- [ ] `count=n` 原生批量(目前是逐次呼叫模擬)

### Phase 5 — 音訊與字幕
- [ ] TTS 配音(ElevenLabs 或 OpenAI TTS)
- [ ] 背景音樂上傳 / 選配
- [ ] 字幕時間軸(Whisper 對齊)
- [ ] Web Console:配樂/配音步驟 + 試聽
- [ ] Composition Engine 疊音軌 + 燒字幕

### Phase 6 — 延伸(Extend)與 pCloud
- [ ] Video Provider 加 `extend()`(5 秒為單位延長)
- [ ] Web Console:選定影片後「是否延伸」選項
- [ ] pCloud WebDAV 實際上傳(取代目前保存佔位)

### Phase 7 — 成本與重試治理
- [ ] 呼叫前檢查當日/當月預算上限(目前只有單次 run 雛形 `_check_budget`)
- [ ] 失敗自動重試(上限次數)+ 成本計入(×1.3~1.5 係數)
- [ ] 定期把各 Provider 實際單價寫回設定檔
- [ ] Web Console 成本儀表板

### Phase 8 — Docker 化與部署
- [ ] 拆 `web-frontend` / `web-backend` / `worker` 三容器
- [ ] `docker-compose.yml` + `.env`
- [ ] 接既有 Cloudflare Tunnel → HostDzire VPS
- [ ] worker 與 backend 分開(長任務不卡 API)

### Phase 9 — 排程與觸發
- [ ] 視需求接 n8n(定時產出 / Webhook 觸發)

### Phase 10 — YouTube Shorts 實作
- [ ] 申請 OAuth2 用戶端
- [ ] `videos.insert` 上傳,直式自動歸類 Shorts
- [ ] 把 Web Console 的 Coming Soon 換成真正發布

---

## 🧱 跨階段基礎(建議穿插做)

### Supabase 持久化(取代記憶體 store)
- [ ] 資料表:`projects` / `storyboards` / `characters` / `assets` / `jobs` / `cost_log` / `publish_log`
- [ ] `jobs` 狀態含 `awaiting_selection`(記憶體 store 已有雛形)
- [ ] Web store 從記憶體改接 Supabase
- [ ] `assets` 記 provider / cost / status / `is_selected`

### 任務佇列
- [ ] 目前用 threading;評估 asyncio Task Queue,長遠接 worker 容器(Phase 8)

---

## 🧹 技術債 / 雜項
- [ ] OpenAI 版分鏡 Provider(目前只有 anthropic)
- [ ] 真正對 fal.ai 做一次 live 煙霧測試(目前只驗證 dry-run)
- [ ] 前端 job 狀態可考慮 WebSocket 取代輪詢(README 提到二擇一)
- [ ] 媒體檔清理 / 專案生命週期(`output/` 會長大)
- [ ] 處理 TestClient 的 httpx deprecation warning

---

## ✅ 完成定義(Definition of Done)
一個項目算完成需要:**程式改好 + 對應測試 + `python -m pytest` 綠 + CI 綠 + 更新本 `TODO.md`**。
