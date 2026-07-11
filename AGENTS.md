# AGENTS.md — CrazySoul Agent 指引

本檔適用於整個 repository。所有在本 repo 工作的 agents / automation 在開始任何修改前都必須遵守以下規則。

## 必讀文件

1. **先閱讀 `CLAUDE.md`** — 這是本專案的人類維護者為 agents 準備的主要開發指引。
2. **再閱讀 `TODO.md`** — 這是開發待辦的單一事實來源；除非使用者明確指定其他任務，否則從「🔜 下一步」最靠前、未勾選的項目開始。
3. 視任務需要再閱讀 `README.md`，並遵循其中「實作階段建議」的 Phase 順序。

## 工作規則摘要

- 使用者明確要求優先於 `CLAUDE.md` / `TODO.md` / `README.md`。
- 每次完成程式修改後，依 `CLAUDE.md` 的 Definition of Done 補上或更新測試，並更新 `TODO.md`。
- 註解與文件以繁體中文為主；Python 識別字維持英文。
- 憑證一律走環境變數或 `.env`，不得寫入程式碼或版控。
- 測試優先使用 `python -m pytest -q`。

若本檔與更深層目錄的 `AGENTS.md` 衝突，較深層檔案只在其目錄範圍內優先；直接的 system / developer / user 指令永遠最高優先。
