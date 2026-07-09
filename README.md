# AI 圖影內容生成工作流

自動化短影音生產管線。核心目標:成本可控、Provider 可替換、角色一致性有保障。

---

## 設計原則

1. **影片是成本中心,圖片不是** — 管線設計圍繞「如何少生成影片秒數」,不是「如何少生成圖片張數」。
2. **Provider 永遠可替換** — 業務邏輯不綁死任何一家 AI 廠商。今天 Kling 漲價,明天換 Wan,不動業務程式碼。
3. **先跑通,再抽象** — MVP 階段先用單一 vendor 打通全流程,拿到真實的 API 行為之後再做介面抽象,不憑空設計。
4. **角色一致性是及格線,不是加分項** — 沒有一致性,片子直接不能用。

---

## 架構總覽

```
[0] Web Console (人機協作介面)
     │  上傳素材、觸發生成、批量生成 n 個、人工挑選、決定延伸與否
     ▼
Prompt / 主題
     │
     ▼
[1] Storyboard Generator (LLM)
     │  拆解成分鏡 JSON:每個分鏡的畫面描述、鏡頭類型、是否需要動態
     ▼
[2] Character DB
     │  角色參考圖、seed、一致性參數,供後續生成呼叫
     ▼
[3] Image Provider Layer  ──→  Flux / SDXL / GPT-Image (可替換)
     │  依 storyboard 逐分鏡「批量生成 n 張」,回傳 Web Console 供人工挑選
     ▼
     ★ 人工挑選一張 ★
     ▼
[4] Routing Decision
     │  依分鏡標記,分流到「動態」或「靜態」兩條路徑
     │
     ├── 需要動態 → [5a] Video Provider Layer ──→ Kling / Wan / Runway / Luma (可替換)
     │                「批量生成 n 段」,回傳 Web Console 供人工挑選
     │                ★ 人工挑選一段 → 是否延伸(Extend)？★
     │
     └── 靜態即可 → [5b] Motion Engine (FFmpeg) ──→ zoompan / pan / parallax / fade
     │
     ▼
[6] Audio Layer
     │  Web Console 上傳/選擇配樂,TTS 配音 + 字幕時間軸
     ▼
[7] Composition Engine (FFmpeg)
     │  影片段 + 動態圖段 + 音軌 + 字幕 → 合成最終 MP4
     ▼
[8] Storage & Publish
     │  成品 → pCloud (WebDAV)
     │  同步發布 → YouTube Shorts (YouTube Data API v3)
     │  素材/成本/版本紀錄 → Supabase
     ▼
[9] Cost & Retry Guardrail
     貫穿全流程,不是獨立的一個階段
```

人工挑選的兩個節點(圖片、影片)本質上是把「失敗重試」的判斷權交給人,取代機器盲目重跑,同時也是唯一能做品質把關的地方——批量生成的意義正是在這裡:生 n 個選 1 個,比生 1 個賭運氣划算,也比全部丟給機器判斷準。

---

## 技術棧

| 項目 | 選擇 | 理由 |
|---|---|---|
| 主語言 | **Python** | 個人專案偏好,生態成熟,各家 AI API 都有現成 SDK |
| 資料庫 | **Supabase (Postgres)** | 個人專案偏好,免費額度夠用,內建 Storage 可放縮圖 |
| 任務排程 | **Python asyncio + Task Queue**(初期);視需求可接 **n8n**(已有自架環境) | 初期不需要引入額外系統,n8n 留給未來做外部觸發或排程 |
| 影片合成 | **FFmpeg**(CLI,Python 用 subprocess 呼叫) | 免費、穩定、zoompan/parallax 濾鏈就能做到 90% 效果,不引入 Godot/Remotion 這種額外維運負擔 |
| 儲存 | **pCloud(WebDAV)** | 現有資源,2TB 空間 |
| Web 後端 | **FastAPI(Python)** | 跟 Pipeline 同語言,直接呼叫既有模組,不用另外做跨語言橋接 |
| Web 前端 | **React(TypeScript)+ Vite**,或直接用 **Next.js** | 個人偏好 TypeScript,單人維護的內部工具不需要過重框架 |
| Web 視覺風格 | **lazyrhythm-design(Nord × Brutalism)**,Dashboard 場景預設 `STRUCTURE 6 / MOTION 3` | 個人設計系統,冷色調 + 偏移陰影結構感,不用另外設計一套風格 |
| 身份驗證 | 單一密碼(環境變數存 hash,登入後發 session cookie) | 單人使用,不需要帳號系統 |
| 影片發布 | **YouTube Data API v3**(`videos.insert`)— **暫緩實作,UI 先放 Coming Soon** | 官方標準上傳介面,直式短影音符合條件會自動歸類為 Shorts |
| 部署 | **Docker + Docker Compose**,搭配既有 **Cloudflare Tunnel** 路由到 HostDzire VPS | 跟你既有的 auto-deploy 工作流一致,單一 `docker-compose up` 起完整服務 |

---

## 模組說明

### 0. Web Console
- **視覺風格**:套用 `lazyrhythm-design` 個人設計系統(Nord × Brutalism),場景定位為 Dashboard,預設 `STRUCTURE_WEIGHT 6 / MOTION_INTENSITY 3`——冷色調背景、偏移陰影卡片、frost 藍系強調色,不另外設計風格。批量生成的縮圖牆用卡片網格呈現,選中狀態用 frost1 邊框標示。
- **身份驗證**:單一密碼登入,環境變數存密碼 hash,登入後發 session cookie,不做帳號系統、不做角色權限。
- **功能**:整個工作流的操作介面,是人機協作的入口,不是單純的後台監控頁面。
  - 上傳角色參考圖 → 寫入 Character DB。
  - 輸入主題/大綱 → 觸發 Storyboard Generator。
  - 每個分鏡「一次生成 n 張圖」(n 為使用者輸入的數字)→ 縮圖牆呈現 → 點選其中一張。
  - 針對選中的圖「一次生成 n 段影片」→ 逐一預覽 → 點選其中一段。
  - 選定影片段後跳出「是否延伸(Extend)」選項,延伸則再呼叫一次 Video Provider 做 5 秒延長。
  - 配樂/配音步驟:可上傳自己的音樂,或觸發 TTS 生成配音,兩者皆可預覽試聽。
  - 最終預覽整支合成影片 → 「保存至 pCloud」按鈕為主要動作;「發布至 YouTube Shorts」按鈕先顯示為 **Coming Soon**(disabled 狀態,不接 API),介面預留位置但不實作,等主流程穩定後再開發。
- **API**:無外部 API,是自建的 FastAPI 後端 + 前端頁面,呼叫下面各模組的內部函式/工作佇列。
- **關鍵設計**:每個生成節點都是「非同步任務」,前端輪詢或用 WebSocket 通知完成狀態,避免使用者對著轉圈圈的頁面等 n 張圖同時生成完。

### 1. Storyboard Generator
- **功能**:輸入主題/大綱文字,輸出結構化分鏡 JSON(場景描述、鏡頭運動類型、角色出場、預估時長、是否標記為「需要動態」)。
- **API**:OpenAI API 或 Anthropic API(擇一,皆為業界標準的 LLM API)。
- **輸出格式**:JSON,直接寫入 Supabase `storyboards` 表。

### 2. Character DB
- **功能**:管理角色的參考圖、固定 seed、風格參數。生圖時帶入參考圖(IPAdapter 類型的 reference 機制)或使用平台原生的角色一致性功能(部分新一代模型如 Kling 3.0 已內建多角度一致性)。
- **API**:依所選 Image Provider 是否支援 reference-image 或 IPAdapter 而定,不是獨立 API,是資料表 + 呼叫參數。
- **資料表**:`characters`(角色名稱、參考圖 URL、seed、風格 tag)。

### 3. Image Provider Layer
- **功能**:統一介面 `image.generate(prompt, character_ref=None, count=n)`,底層決定呼叫哪家模型,支援一次請求生成 n 張(多數 API 原生支援批量參數,或用平行呼叫模擬)。
- **候選 API**(初期只接一家,之後再擴充):
  - **Flux(經由 fal.ai 或 Replicate API)** — 主力,便宜且文字渲染能力強。
- **輸出**:n 張圖片 URL/binary 清單 + 各自成本紀錄,狀態標記為「待挑選」,交給 Web Console 呈現。

### 4. Routing Decision
- **功能**:純邏輯層,不呼叫外部 API。依 storyboard 標記或簡單規則(例如每 3 個分鏡只有 1 個走動態)決定分流路徑。
- **這是控制成本的核心開關**,建議把「動態分鏡比例」做成可調參數,方便之後 A/B 測試成本與效果。

### 5a. Video Provider Layer
- **功能**:統一介面 `video.generate(image, duration, motion_hint, count=n)`,底層可替換模型,支援一次生成 n 段供挑選;另提供 `video.extend(selected_clip)` 做延伸生成(多數影片模型原生支援 5 秒為單位延長)。
- **候選 API**(初期只接一家):
  - **Kling(經由 fal.ai 或官方 API)** — 目前性價比高,支援 image-to-video 與延伸(Extend)。
  - 預留擴充:Wan(更便宜)、Runway、Luma。
- **輸出**:n 段影片片段 + 成本紀錄,狀態標記為「待挑選」;確認延伸後追加一段並自動接續。

### 5b. Motion Engine
- **功能**:對靜態圖套用 FFmpeg 濾鏈(zoompan 做 zoom/pan、疊圖模擬 parallax、fade 轉場),產生「看起來在動」的影片片段,成本趨近於零。
- **API**:無,純本地 FFmpeg CLI。
- **這是壓低成本的關鍵模組**,優先度高於外部影片 API。

### 6. Audio Layer
- **功能**:文字轉語音配音、背景音樂選配、字幕時間軸生成(可用 Whisper 做語音對齊)。
- **候選 API**:
  - **ElevenLabs** 或 **OpenAI TTS** — 配音。
  - **OpenAI Whisper API**(或本地跑)— 字幕時間軸。

### 7. Composition Engine
- **功能**:把所有影片片段(動態 API 生成 + Motion Engine 生成)、音軌、字幕,依 storyboard 順序用 FFmpeg 合成最終 MP4。
- **API**:無,本地 FFmpeg。

### 8. Storage & Publish
- **功能**:
  - 成品影片與素材 → 透過 WebDAV 上傳 pCloud。
  - ~~成品同步發布至 YouTube Shorts~~ — **暫緩(Coming Soon)**:UI 保留按鈕位置,後端不實作,待主流程穩定後再開發。
  - 每個任務的 prompt、模型版本、成本、生成時間、成功/失敗狀態 → 寫入 Supabase。
- **API**:pCloud WebDAV API、Supabase REST/Client SDK。**YouTube Data API v3 暫不接入**,待 Coming Soon 功能開發時再申請 OAuth2 用戶端。
- **資料表**:`assets`(素材紀錄)、`jobs`(任務狀態)、`cost_log`(成本明細)、`publish_log`(預留給未來發布功能,現階段不寫入)。

### 9. Cost & Retry Guardrail
- **功能**:貫穿全流程的橫切關注點,不是獨立階段。
  - 每次呼叫外部 API 前檢查是否超出當日/當月預算上限。
  - 失敗自動重試(上限次數),重試成本計入預估(建議抓 1.3~1.5 倍係數)。
  - 定期把各 Provider 的實際單價寫回設定檔,因為這個市場價格波動大(半年內漲跌 40% 以上是常態)。

---

## 資料庫規劃(Supabase)

| 表名 | 用途 |
|---|---|
| `projects` | 專案基本資訊 |
| `storyboards` | 分鏡 JSON,關聯 project |
| `characters` | 角色參考圖、seed、風格 |
| `assets` | 生成的圖片/影片素材,含 provider、cost、status、`is_selected`(是否為人工挑選結果) |
| `jobs` | 任務佇列狀態(pending / awaiting_selection / processing / done / failed) |
| `cost_log` | 每次 API 呼叫的實際花費,用於預算追蹤與事後分析 |
| `publish_log` | 發布紀錄:pCloud 路徑、YouTube 影片 ID、發布時間、發布狀態 |

`jobs` 表新增 `awaiting_selection` 狀態,對應 Web Console 的兩個人工挑選節點——批量生成完成後任務停在這個狀態,等使用者在介面上點選,才繼續往下一步。

---

## 部署(Docker)

目標環境:HostDzire VPS,搭配既有的 Cloudflare Tunnel 路由(比照你既有的 auto-deploy 工作流)。

**容器拆分:**

| 服務 | 說明 |
|---|---|
| `web-frontend` | React/Next.js 前端,build 後靜態檔案 |
| `web-backend` | FastAPI,處理所有 API 請求與任務派發 |
| `worker` | 實際執行生成任務的背景 worker(呼叫 Image/Video Provider、跑 FFmpeg),與 backend 分開容器,避免長任務卡住 API 回應 |
| `ffmpeg`(內建於 worker image) | 不需要獨立容器,裝在 worker image 裡即可 |

**外部依賴(不進容器,走既有服務):**
- Supabase — 用雲端託管版本,不需要自架 Postgres 容器。
- pCloud — 外部儲存,WebDAV 呼叫即可。

**部署方式:**
- 一份 `docker-compose.yml` 定義上述容器,`.env` 存所有 API Key、密碼 hash、Supabase 連線字串。
- Cloudflare Tunnel 指向 `web-frontend` 的對外 port,不需要額外開防火牆 port。
- 沿用你既有的 auto-deploy 流程(GitHub repo → 部署腳本 → Docker 起服務 → Tunnel 掛上網域)即可套用在這個專案上,不需要另外設計部署流程。

---

## 實作階段建議(照這個順序做,不要跳著做)

1. **Phase 0 — 打通單一路徑(CLI/腳本即可,不做 UI)**:LLM 出分鏡 → Flux 生圖 → Kling 生成全部動態片段(先不分流)→ FFmpeg 硬串接 → 手動丟 pCloud。目標是驗證資料流,不追求成本優化,也不追求介面。
2. **Phase 1 — 加入 Motion Engine**:導入 Routing Decision,部分分鏡改用 FFmpeg zoompan/pan,不再全部呼叫影片 API。這一步直接大幅降低成本。
3. **Phase 2 — 角色一致性**:建立 Character DB,生圖時帶入參考圖。
4. **Phase 3 — Provider 抽象層**:把 Image/Video Provider 包成統一介面,新增第二家 provider 驗證抽象是否成立,同時把 `count=n` 批量參數補上。
5. **Phase 4 — Web Console(最小可用版)**:FastAPI 包一層 API,前端做「批量生成 → 縮圖牆挑選 → 下一步」這條主線,先不做美化,能點就好。這一步是體驗成型的關鍵,建議提前到這裡而不是排最後,因為有了 UI 才能真正開始「大量產出、大量挑選」的日常使用循環。
6. **Phase 5 — 音訊與字幕自動化**:接入 TTS、Whisper 字幕對齊,整合進 Web Console 的配樂配音步驟。
7. **Phase 6 — 延伸(Extend)串接**:Video Provider 加上 `extend()`,Web Console 加上延伸選項與「保存至 pCloud」按鈕;「發布至 YouTube Shorts」按鈕做成 Coming Soon 佔位,不接實作。
8. **Phase 7 — 成本與重試治理**:預算上限、失敗重試係數、成本儀表板,呈現在 Web Console 上讓你隨時看到花費。
9. **Phase 8 — Docker 化與部署**:拆成 `web-frontend` / `web-backend` / `worker` 三個容器,寫 `docker-compose.yml`,接上既有 Cloudflare Tunnel,部署到 HostDzire VPS。
10. **Phase 9 — 排程與觸發自動化**:視需要接入 n8n 做外部觸發(例如定時產出、Webhook 觸發)。
11. **Phase 10 — YouTube Shorts 實作**:等前面都跑穩了再回頭做,申請 OAuth2 用戶端、接 `videos.insert`,把 Coming Soon 換成真正的發布功能。

---

## 明確不做的事(避免過度工程)

- **不引入 Godot 或其他遊戲引擎當合成工具**:FFmpeg 濾鏈就能達到 90% 效果,額外引擎的維運成本(headless 渲染穩定性、部署複雜度)不划算。
- **不在 Phase 0 就設計完美的 Provider 抽象層**:先跑通一家,再抽象,避免脫離現實的過度設計。
- **不省略重試成本估算**:預算永遠抓實際單價 × 1.3~1.5,不要用官方報價當最終成本。
- **不做多使用者權限系統**:單人使用的內部工具,Web Console 不需要角色權限、多租戶這類設計,頂多加一層簡單密碼或 IP 白名單。
