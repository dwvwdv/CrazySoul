# TODO — CrazySoul 開發待辦

> 這份清單是開發的**單一事實來源**。
> 每次開發**前**先讀這裡,從「🔜 下一步」挑最靠前、未勾選的項目做;
> 開發**完成後**回來勾選,並補上新發現的子任務 / 技術債。
> 順序原則:照 `README.md`「實作階段建議」逐 Phase 做,不跳著做
> (Phase 4 Web Console 已依 README 建議提前完成)。跨階段基礎可穿插。

---

## ✅ 已完成
- [x] **Phase 0** — 打通單一路徑(LLM 分鏡 → 生圖 → 生影片 → FFmpeg 串接),CLI + dry-run
- [x] **Phase 1** — Routing Decision:依 `needs_motion` + 動態比例上限分流(Video Provider / Motion Engine)
- [x] **Phase 2** — Character DB:角色資料結構 + Web 上傳參考圖 + 分鏡標記出場角色 + 生圖帶入一致性
- [x] **Phase 3** — Provider 抽象層:統一 `ImageProvider`/`VideoProvider` 介面 + 註冊表 + 第二家(fal-sdxl / fal-wan)+ `count=n` 原生批量
- [x] **Phase 4** — Web Console 最小可用版(登入 → 批量生成 → 縮圖牆挑選 → 合成 → 保存佔位)
- [x] 縮圖牆批量候選(`count=n`,dry-run 佔位圖顏色由 seed 決定,肉眼可分辨)
- [x] lazyrhythm-design 基礎風格(Nord × Brutalism)
- [x] CI(GitHub Actions,Python 3.11 / 3.12)+ 測試 52 項

---

## 🔜 下一步(建議順序)

### Phase 1 — Routing Decision(降成本核心,優先)✅
- [x] 依 storyboard 的 `needs_motion` 分流:需要動態 → Video Provider;靜態即可 → Motion Engine(FFmpeg zoompan)。新增 `crazysoul/routing.py`(`decide_routes` / `render_clip`)
- [x] 「動態分鏡比例」做成可調參數(`Config.dynamic_ratio` + env `DYNAMIC_RATIO` + CLI `--dynamic-ratio` + Web 新專案「動態比例 %」)
- [x] Web Console 每個分鏡顯示走哪條路徑(徽章 + `needs_motion`),並可手動覆寫(`POST /shots/{idx}/route`)
- [x] 測試:分流邏輯單元測試 + 混合路徑合成端到端(`tests/test_routing.py`)
- [ ] 後續:路徑已鎖定(生成影片後)時,前端隱藏覆寫鈕的體驗可再優化;live 模式下 Motion Engine 與 Kling 的畫質差異需實測

### Phase 2 — Character DB(角色一致性)✅
- [x] `characters` 資料結構(名稱、參考圖、seed、風格 tag)— `models.Character`
- [x] Web Console:上傳角色參考圖(multipart,存專案目錄,`POST /projects/{pid}/characters`)
- [x] 生圖時帶入一致性:seed 走平台原生參數、style_tag 併入 prompt、ref_image 供 reference/IPAdapter
- [x] 分鏡可標記出場角色(`POST /shots/{idx}/characters`),生圖自動帶入
- [ ] 後續:真正的 reference / IPAdapter live 實作(目前 live 僅帶 seed + style_tag;ref_image 已保存待接);角色庫接 Supabase 持久化

### Phase 3 — Provider 抽象層 ✅
- [x] 統一介面 `image.generate_images(ImageRequest, out_paths)` / `video.generate_clips(VideoRequest, out_paths)`(見 `providers/base.py`)
- [x] 新增第二家 provider(image: fal-sdxl;video: fal-wan)驗證抽象成立,以字串選 Provider
- [x] `count=n` 原生批量(flux `num_images=n` 一次呼叫;dry-run 一次產多張)
- [ ] 後續:第二家的 live 端點與回傳格式需實測(目前僅驗證 dry-run 與介面一致性);Web UI 可加 Provider 選擇下拉

### Phase 5 — 音訊與字幕
- [x] TTS 配音(OpenAI TTS live + dry-run 佔位音訊,CLI `--voiceover` 可混入 final.mp4)
- [x] 背景音樂上傳 / 選配
- [x] 字幕時間軸(Whisper/live segments + dry-run heuristic SRT)
- [ ] Web Console:配樂/字幕步驟已接;配音步驟 + 試聽仍待 UI
- [x] Composition Engine 疊音軌 + 燒字幕(TTS 旁白 mux、背景音樂、SRT 燒字幕已接)

### Phase 6 — 延伸(Extend)與 pCloud
- [x] Video Provider 加 `extend()`(5 秒為單位延長;dry-run 本地循環,live provider 介面已預留)
- [x] Web Console:選定影片後「是否延伸」選項
- [x] pCloud WebDAV 實際上傳(取代目前保存佔位;dry-run/未設定時仍標記佔位)

### Phase 7 — 成本與重試治理
- [x] 呼叫前檢查當日/當月預算上限(本次 run 預算上限 + Web 成本摘要;日/月跨 run 持久化留待 Supabase)
- [x] 失敗自動重試(上限次數)+ 成本計入(×1.3~1.5 係數)
- [x] 定期把各 Provider 實際單價寫回設定檔(`config/provider_prices.json` + loader)
- [x] Web Console 成本儀表板

### Phase 8 — Docker 化與部署
- [x] 拆 `web-frontend` / `web-backend` / `worker` 三容器
- [x] `docker-compose.yml` + `.env.example`
- [x] 接既有 Cloudflare Tunnel → HostDzire VPS(README / compose ports 已預留)
- [x] worker 與 backend 分開(Compose profile 預留 worker 服務;實際佇列替換仍在任務佇列技術債)

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
