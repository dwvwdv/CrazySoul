# CLAUDE.md — CrazySoul 開發指引

給在這個 repo 工作的 Claude 的常駐指引。**每次進來先讀這份與 `TODO.md`。**

## 開發流程(最重要)

1. **開始開發前,先讀 `TODO.md`**,從「🔜 下一步」挑最靠前、未勾選的項目來做。
   若使用者當下有明確指定,以使用者為準。
2. 遵循 `README.md`「實作階段建議」的順序,逐 Phase 做、**不跳著做**
   (Phase 4 Web Console 已依 README 建議提前完成)。跨階段基礎(Supabase 持久化)可穿插。
3. **每次開發完成後,一定要更新 `TODO.md`**:
   - 把完成的項目打勾(`[x]`)。
   - 補上開發過程中**新發現**的子任務、技術債、後續事項。
   - 需要時調整「🔜 下一步」的順序。
4. 持續這個循環,**直到 `TODO.md` 全部清空、整個專案完善為止**。

> 這是一份持續推進的契約:讀 TODO → 做一件事 → 更新 TODO → 再讀 TODO。不要停在半途。

## 完成定義(Definition of Done)

一件事算完成,需要全部滿足:
**程式改好 + 對應測試 + `python -m pytest` 綠 + CI 綠 + 更新 `TODO.md`**。缺一不算完成。

## 專案慣例

- **語言 / 風格**:Python;註解用繁體中文;識別字(identifier)用英文。
- **憑證**:一律走環境變數 / `.env`(已 gitignore),絕不寫進程式或版控。
- **Provider 可替換**:業務邏輯用字串選 Provider,不綁死任何一家 SDK。先跑通一家,再抽象。
- **影片合成**:一律用 FFmpeg,不引入 Godot / Remotion。
- **dry-run**:每個生成節點都要能離線 dry-run(用 FFmpeg 佔位素材),測試不需憑證或網路。
- **測試**:放在 `tests/`,用 `python -m pytest`;CI 在 Python 3.11 / 3.12 跑。
- **分鏡 LLM**:預設 Anthropic(model id `claude-opus-4-8`),用 structured outputs 強制輸出合法 JSON;可替換成 OpenAI。

## 常用指令

- 離線跑管線:`python -m crazysoul.cli --prompt "…" --dry-run`
- 啟動 Web Console:`CRAZYSOUL_DRY_RUN=1 python -m crazysoul.web`(預設密碼 `crazysoul`)
- 測試:`python -m pytest -q`

## 目錄

- `crazysoul/` — 核心管線(`storyboard` / `providers` / `ffmpeg` / `pipeline` / `config`)
- `crazysoul/web/` — Web Console(FastAPI + 內嵌 SPA)
- `tests/` — 測試
- `TODO.md` — 待辦(單一事實來源)
- `README.md` — 產品規格與階段規劃

## Git

- 開發分支:`claude/development-start-1ighoz`。
- push 後若該分支沒有開啟中的 PR 就開一個(ready for review)。
- commit / PR 描述用繁體中文。
