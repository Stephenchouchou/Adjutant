# LLM Wiki 知識庫整合

**Date:** 2026-04-07
**Type:** Feature

## Summary

整合 Karpathy 的 LLM Wiki 模式到 Adjutant，新增持久化 wiki 知識層。LLM 持續建構和維護結構化 wiki（摘要、實體、概念、比較頁面），取代每次查詢都從零開始的純 RAG 模式。

## Changes

### New Files
- `src/adjutant/core/wiki.py` — WikiManager 核心模組（~320 行）
  - `init_wiki()`: 建立 wiki 目錄結構、_schema.md、index.md、log.md
  - `ingest(source)`: 消化來源文件，LLM 產出 JSON 計畫，多檔案寫入
  - `query(question)`: 兩階段查詢（index.md → pages → 綜合回答）
  - `lint()`: wiki 健康檢查（矛盾、孤立、缺少交叉引用）
  - `get_wiki_context_for_chat()`: 自動注入 chat prompt
- `src/adjutant/prompts/wiki_schema.md` — wiki 規範模板（init 時複製到 wiki/_schema.md）
- `src/adjutant/prompts/wiki_ingest.md` — ingest prompt 模板

### Modified Files
- `src/adjutant/config.py` — NotebookPaths 加 `wiki_dir` 欄位
- `src/adjutant/core/chat.py` — `build_chat_prompt()` 加 `wiki_context` 參數
- `src/adjutant/__main__.py` — 新增 `wiki` CLI 子命令群（init/ingest/query/lint/status/pages），REPL 自動注入 wiki context
- `src/adjutant/mcp/server.py` — 5 個新 wiki MCP tools
- `src/adjutant/web/server.py` — wiki REST API endpoints + graph data API + WebSocket wiki context 注入
- `src/adjutant/web/static/index.html` — Wiki modal（GRAPH/PAGES/VIEW 三分頁）+ 頂部 WIKI stat block
- `src/adjutant/web/static/style.css` — wiki 相關樣式（graph、page list、page viewer）
- `src/adjutant/web/static/app.js` — wiki modal 邏輯 + force-directed graph view（Canvas 2D）+ 命令面板整合
- `CLAUDE.md` — 更新架構文件

## Architecture

```
notebook_root/
  wiki/                    ← LLM 維護的知識庫（新增）
    _schema.md             ← wiki 慣例與規範
    index.md               ← 全頁面索引（分類表格）
    log.md                 ← 操作���誌
    summaries/             ← 來源摘要頁
    entities/              ← 實體頁（人、工具、專案）
    concepts/              ← 概念頁（方法論、框架）
    comparisons/           ← 比較分析頁
```

三層架構：Raw sources（不動）→ Wiki（LLM 維護）→ Schema（規範）

## Web UI Features

- **Graph View**: force-directed 互動圖，節點按分類著色，可拖拽/縮放/雙擊開啟
- **Page Browser**: 分類頁面清單
- **Page Viewer**: Markdown 渲染，wiki 內部連結可點擊跳轉
- **Top Bar**: 📚 WIKI stat block 顯示頁面數

### Phase 2: Web UI 檔案編輯 + Wiki 操作補完

**New API Endpoints:**
- `POST /api/files/write` — 安全寫入筆記檔案
- `POST /api/wiki/lint` — Wiki 健康檢查
- `POST /api/wiki/page` (POST) — 寫入 wiki 頁面

**File Viewer → Editor 升級:**
- EDIT/SAVE/CANCEL 按鈕，在 view 和 edit 模式之間切換
- Markdown 預覽和原始碼編輯

**Wiki 操作面板:**
- INGEST 按鈕：開啟 file browser 選擇來源檔案，一鍵 ingest
- LINT 按鈕：執行健康檢查，結果顯示在 chat feed
- Wiki 頁面編輯：VIEW tab 加 EDIT 按鈕，可手動修正 wiki 頁面
