# Adjutant — 專案計畫

## 願景

Adjutant 是一個 **個人知識管理副官**（參謀與書記官），建立在「最小人工 + 最大 AI」的核心理念上。

使用者負責：**捕捉、標記意圖、寫現場觀察**（佔 30%）
Adjutant 負責：**分類歸檔、提取完成項、生成週報、關聯舊筆記、提醒卡住的任務**（佔 70%）

Adjutant 不是第二大腦，不是唯一的 source of truth。
使用者的筆記系統（inbox.md、tasks.md、daily/*.md、projects/*）才是正式紀錄。
Adjutant 站在這套系統上運作，負責整理、彙整、提醒。

---

## 核心角色定義

Adjutant 的角色是 **StarCraft 中的副官（Adjutant）**：

- 接收指揮官（使用者）的指令，執行標準作業流程
- 掃描戰場資訊（筆記系統），產出情報摘要
- 提醒指揮官被遺忘的任務、過期的 deadline、卡住的項目
- 不替指揮官做決定，但提供可執行的建議
- 溝通風格：簡潔、直接、軍事化語調、繁體中文

---

## 人機分工 SOP

| 環節 | 誰做 | 怎麼做 |
|------|------|--------|
| **捕捉** | 使用者 | 隨手記到 inbox.md，格式隨意 |
| **意圖標記** | 使用者 | 快速掃 inbox，貼標籤（#task #note #project #someday） |
| **分類歸檔** | Adjutant | `adjutant triage` — 讀取 inbox，按標籤分類到對應位置 |
| **當天紀錄** | 使用者 | Daily note 只寫 Log + Experiment（現場才能記的東西） |
| **日報彙整** | Adjutant | `adjutant daily` — 從 daily note 提取 Completed / Carry Forward / Insights |
| **週報** | Adjutant 草稿 + 使用者修改 | `adjutant weekly` — 掃描 7 天 daily notes，產出週報草稿 |
| **任務追蹤** | 使用者決定 + Adjutant 提醒 | `adjutant tasks` — 掃描 tasks.md，找出 stale/blocked 項目 |
| **知識搜尋** | Adjutant | `adjutant chat` — 回答關於筆記系統內容的問題 |
| **優先級判斷** | 使用者 | AI 不知道老闆今天心情怎樣、哪個 deadline 可以延 |

---

## 系統架構

```
使用者的筆記系統（ZKNote）
├── inbox.md              ← 使用者捕捉
├── tasks.md              ← 使用者管理 + Adjutant 掃描
├── journal/daily/*.md    ← 使用者寫 Log + Experiment
└── projects/*            ← 專案狀態與實驗脈絡

Adjutant 應用
├── CLI（adjutant）       ← 終端機直接使用
├── Web UI（adjutant web）← 戰情簡報室介面
├── SOP 引擎              ← 標準作業流程模板
└── Session 管理          ← 對話紀錄
```

---

## 介面

### CLI 模式
- `adjutant` — REPL 互動模式
- `adjutant chat "問題"` — 單次對話
- `adjutant triage` — 執行 inbox 分類 SOP
- `adjutant daily` — 執行日報 SOP
- `adjutant weekly` — 執行週報 SOP
- `adjutant tasks` — 執行任務掃描 SOP
- `adjutant sop list` — 列出所有 SOP
- `adjutant sop run <key>` — 執行指定 SOP
- `adjutant sop new <key>` — 建立自訂 SOP
- `adjutant web` — 啟動 Web UI

### Web UI 模式（戰情簡報室）
- 中央 Adjutant 頭像（StarCraft 風格 CRT 效果）
- SOP 快捷按鈕列
- 戰情簡報面板（對話區域）
- 底部指令輸入 + 狀態列
- WebSocket 即時串流回應

---

## 目前進度

### 已完成
- [x] 專案骨架（pyproject.toml, Click CLI）
- [x] Config 管理（~/.adjutant/config.toml）
- [x] AI CLI Dispatcher（串流子程序執行）
- [x] Chat 模組（persona + 對話歷史 + 串流）
- [x] SOP 引擎（markdown + YAML frontmatter 模板）
- [x] Session 模型（Pydantic, JSON 持久化）
- [x] 四個內建 SOP（inbox-triage, daily-summary, weekly-report, task-update）
- [x] Web UI — FastAPI + WebSocket server
- [x] Web UI — 戰情簡報室前端（StarCraft 風格）
- [x] CLI REPL 模式

### 待開發
- [x] Adjutant persona 強化 — 讓 AI 真正理解自己的角色和使用者的筆記系統結構
- [x] SOP 執行結果寫回檔案（CLI 確認 + Web UI 確認 UI）
- [ ] 多 AI 工具支援測試（gemini, codex）
- [x] Session 歷史瀏覽（Web UI modal + CLI /history）
- [x] 筆記系統自動偵測（首次 init 時掃描目錄結構）
- [x] Session 接續（CLI REPL 啟動時可接續近 30 分鐘內的 session）
- [ ] 定時提醒功能（cron-like 排程）
- [ ] 跨 session 記憶（長期記憶持久化）

---

## 技術棧

- Python 3.12+
- Click（CLI）
- Pydantic（資料模型）
- Rich（終端格式化）
- FastAPI + Uvicorn（Web server）
- WebSocket（即時串流）
- AI CLI: claude（預設），支援 gemini / codex

---

## 設計原則

1. **使用者的筆記系統是 source of truth** — Adjutant 讀取、分析、建議，但不擅自修改
2. **SOP 驅動** — 所有自動化工作流都透過可編輯的 SOP 模板定義
3. **CLI-first, Web-optional** — 終端機是主要介面，Web UI 是補充
4. **單 AI 模式** — 簡化自 CrossVal 的多 AI 架構，專注於一對一副官體驗
5. **最小人工介入** — 使用者只做捕捉、標記、判斷；整理工作交給 Adjutant
