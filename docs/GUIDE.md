# Adjutant 操作指南

完整的操作流程與核心概念說明。

---

## 核心概念

### 指揮官 / 副官模型

Adjutant 採用軍事指揮架構：

- **指揮官（你）**：做所有決策 — 寫什麼、分類到哪、優先順序
- **副官（AI）**：處理情報 — 分類、摘要、提醒、搜尋關聯

副官不會擅自行動。所有 SOP（標準作業程序）的輸出都需要你確認才會寫入檔案。

### 資料流

```
                你的大腦
                   │
                   ▼
┌─────────── 捕獲層 ───────────┐
│  CLI · Web UI · Telegram Bot │
│         ↓                    │
│    inbox.md（收件匣）         │
└──────────────────────────────┘
                   │
                   ▼ adjutant triage
┌─────────── 處理層 ───────────┐
│  tasks.md      任務追蹤       │
│  projects/     專案資料       │
│  notes/        知識筆記       │
│  journal/      每日日誌       │
└──────────────────────────────┘
                   │
                   ▼ adjutant daily / weekly
┌─────────── 回顧層 ───────────┐
│  Daily Summary  每日摘要      │
│  Weekly Report  週報          │
│  Task Update    任務掃描      │
└──────────────────────────────┘
```

### 三層智能

1. **Persona + Directives**（人格層）— 副官的身份定義與觸發指令
2. **RAG + Memory**（記憶層）— 語意搜尋筆記 + 向量記憶，只注入相關上下文
3. **SOP**（執行層）— 標準化的作業流程，可帶參數、多步驟、約束條件

---

## 第一次設置

### 1. 安裝

```bash
git clone https://github.com/Stephenchouchou/Adjutant.git
cd Adjutant
./install.sh
```

安裝過程中會問你：
- Notebook 根目錄路徑（你的筆記資料夾）
- AI 工具（claude / gemini / codex / ollama）
- 是否安裝 sentence-transformers（本地嵌入模型）

### 2. 設定 AI 後端

**方案 A — Claude CLI（推薦，最聰明）：**
```bash
# 確認 claude CLI 已安裝
claude --version
# config.toml 預設就是 claude
```

**方案 B — Ollama（完全本地，免費）：**
```bash
ollama serve                      # 啟動 Ollama
ollama pull llama3.1              # 拉對話模型
ollama pull nomic-embed-text      # 拉嵌入模型（RAG/記憶必需）
```

編輯 `~/.adjutant/config.toml`：
```toml
ai_tool = "ollama"
ai_model = "llama3.1"
```

### 3. 建立搜尋索引

```bash
source .venv/bin/activate
adjutant index build
```

這會掃描你 notebook 裡所有 `.md` 檔案 → 按標題切塊 → 嵌入為向量 → 存入 LanceDB。之後每次 build 只處理修改過的檔案（增量更新）。

### 4. 匯入現有記憶（如果有）

如果你之前用過 `~/.adjutant/memory.md`：
```bash
adjutant memory import
```

這會把平文字記憶轉為向量記憶條目。

---

## 每日操作流程

### 早上

```bash
# 1. 查看 inbox 積累了什麼
adjutant chat "inbox 有什麼需要處理？"

# 2. 分類 inbox
adjutant triage
# → 副官掃描 inbox.md，建議每項歸類到 task / note / project / someday
# → 確認後寫入 inbox.md（已分類的標記為 done）

# 3. 掃描任務
adjutant tasks
# → 找出 stale（>7天）、blocked、quick-win 任務，建議 next actions
```

### 工作中

```bash
# 隨時記錄想法 — CLI
adjutant chat "記錄：API 重構要先處理 auth middleware"
# → 副官判斷這是筆記，加到 inbox.md

# 隨時記錄想法 — Telegram
# 直接發訊息給 bot → 自動判斷是問題還是筆記

# 帶檔案脈絡聊天
adjutant chat --file projects/api-redesign.md "這個重構的下一步是什麼？"

# 語意搜尋筆記
adjutant index search "上次關於 deployment 的討論"
```

### 下班前

```bash
# 生成今日摘要
adjutant daily
# → 掃描今天的 daily note → 產出結構化摘要：
#   - 完成項目
#   - 待處理事項（carry forward）
#   - 洞察 & 筆記
```

### 每週五

```bash
# 週報
adjutant weekly
# → 掃描過去 7 天的 daily notes → 產出週報：
#   - 本週成就
#   - 進行中項目
#   - 下週計劃
```

---

## Web UI 操作

啟動：`adjutant web` → 瀏覽器開 `http://127.0.0.1:8100`

### 頂部狀態列

| 區塊 | 說明 |
|------|------|
| 📥 INBOX | 未處理的 inbox 項目數。點擊看清單 |
| ✅ TASKS | 開放任務數。點擊看清單 |
| 📋 DAILY | 今天有沒有寫 daily note |
| 📁 NOTES | 筆記總數 |
| 🧠 INDEX | RAG 索引狀態。**點擊可建立/重建索引** |
| BOT | Telegram bot 連線狀態。點擊設定 |

### Command Palette（Ctrl+K）

所有操作的入口。按 `Ctrl+K` 叫出，支援模糊搜尋。

**SOP 操作：**
- Inbox Triage — 分類收件匣
- Daily Summary — 今日摘要
- Task Update — 任務掃描
- Weekly Report — 週報

**工具：**
| 項目 | 說明 |
|------|------|
| 🔍 Search Notes | 語意搜尋筆記（需先建索引）|
| 🧠 Build Index | 建立/重建 RAG 向量索引 |
| 📂 Browse Files | 瀏覽筆記本檔案 |
| 🗂️ History | 歷史對話。點擊可**續接對話** |
| 👤 Persona | 編輯副官人格設定 |
| 💾 Memory | 管理向量記憶 + 平文字記憶 |
| ⚡ Directives | 管理觸發指令 |
| ⚙️ Model | 切換 AI 模型 |
| 🔧 Settings | 設定路徑、Ollama URL、Bot |
| 🤖 Telegram Bot | Bot 設定與啟動 |

### 聊天附加檔案

輸入框旁的 📎 按鈕可以附加筆記本檔案。選擇後檔案內容會作為對話脈絡傳給 AI，等同 CLI 的 `--file` 參數。

### SOP v2 參數

如果 SOP 有定義 `inputs:`，Web UI 會自動彈出參數填寫視窗，填完後才執行。

### 寫檔 Diff 預覽

SOP 要寫入檔案時，會顯示現有檔案的預覽，讓你決定 WRITE 或 SKIP。

---

## 記憶系統

### 向量記憶 vs 平文字記憶

| | 向量記憶 | 平文字記憶 |
|---|---------|-----------|
| 儲存 | LanceDB 向量資料庫 | `~/.adjutant/memory.md` |
| 注入方式 | 語意搜尋 → 只注入相關記憶 | 全文注入每次對話 |
| 適合 | 大量記憶（100+條） | 少量關鍵資訊 |
| 搜尋 | 語意相似度 | 無 |
| 管理 | add / search / forget | 手動編輯文字檔 |

**建議**：兩者可以並存。向量記憶存具體事實，平文字記憶存「每次對話都要知道」的核心資訊。

### 記憶分類策略

```
fact        — "ML 專案用 PyTorch"、"部署在 AWS ap-northeast-1"
preference  — "回答用繁體中文"、"程式碼加註解"
instruction — "不要自作主張修改優先級"、"回報時附上來源檔案路徑"
context     — "Stephen 是 team lead"、"Q2 目標是降低 latency 30%"
```

### CLI 操作

```bash
# 新增
adjutant memory add "API v3 用 GraphQL 不用 REST" --category fact

# 語意搜尋
adjutant memory search "API 架構"

# 列出
adjutant memory list
adjutant memory list --category instruction

# 刪除
adjutant memory forget <id>

# 從 memory.md 匯入
adjutant memory import
```

### Web UI 操作

Ctrl+K → Memory：
- **VECTOR 分頁**：新增、搜尋、篩選分類、刪除、匯入
- **FLAT FILE 分頁**：直接編輯 memory.md

---

## SOP 系統

### 內建 SOP

| Key | 用途 | 讀取檔案 |
|-----|------|---------|
| `inbox-triage` | 分類 inbox 項目 | inbox.md |
| `daily-summary` | 今日摘要 | journal/daily/{today}.md |
| `task-update` | 任務狀態掃描 | tasks.md |
| `weekly-report` | 週報 | journal/daily/*.md (最近7天) |

### 自訂 SOP

在 `~/.adjutant/sop/` 建立 `.md` 檔案：

**v1 格式（簡單）：**

```markdown
---
key: standup
label: Standup Report
icon: 🎯
description: 產出 standup 格式的狀態報告
files:
  - "tasks.md"
  - "journal/daily/{today}.md"
output: stdout
---

根據以下資料，產出精簡的 standup 報告：

{file_contents}

格式：
1. 昨天完成
2. 今天計劃
3. 阻礙/風險
```

**v2 格式（進階）：**

```markdown
---
key: project-review
version: "2"
label: Project Review
icon: 📊
description: 審查特定專案的狀態
author: stephen
tags: [projects, review]
inputs:
  - name: project
    type: string
    description: 專案名稱
  - name: depth
    type: string
    default: "summary"
    description: 審查深度 (summary / detailed)
files:
  - "projects/{project}.md"
  - search: "{project} architecture"
output: stdout
tools: [read_file, search_notes]
constraints:
  - "聚焦於可行動的建議"
  - "標注風險等級（高/中/低）"
steps:
  - name: gather
    prompt: |
      閱讀專案資料和相關筆記：
      {file_contents}
      {search_results}
  - name: analyze
    prompt: |
      基於收集的資料：
      {step_context}

      以 {depth} 程度進行審查。
---
```

### SOP 執行流程

```
CLI: adjutant sop run project-review
        │
        ▼
  有 inputs？ ──Y──→ 提示輸入參數
        │                    │
        N                    ▼
        │            resolve_inputs()
        ▼                    │
  is_multistep？ ──Y──→ 逐步執行，前步輸出 → 下步 {step_context}
        │                    │
        N                    ▼
        ▼            build_step_prompt() × N
  build_sop_prompt()         │
        │                    │
        ▼                    ▼
  AI 生成回應 ←──────────────┘
        │
        ▼
  output: file? ──Y──→ diff 預覽 → 確認寫入
        │
        N
        ▼
  輸出到終端
```

---

## Directives 系統

Directives 是觸發式 prompt 注入。當使用者的訊息包含特定關鍵字時，對應的 prompt 會被自動附加到 AI 的輸入中。

### 運作方式

```
使用者輸入: "服從指令，把所有 TODO 標為完成"
                 │
                 ▼
match_directives("服從指令，把所有 TODO 標為完成")
                 │
                 ▼ 找到 trigger: "服從指令"
          注入 obey_command.md 的 body
                 │
                 ▼
AI 收到: persona + directive + user message
```

### 自訂 Directive

在 `~/.adjutant/prompts/directives/` 建立 `.md` 檔案：

```markdown
---
trigger: 詳細分析
---

當指揮官要求「詳細分析」時，請提供：
1. 完整的背景脈絡
2. 優劣比較表格
3. 具體的行動建議，附帶預估工時
4. 潛在風險與緩解措施
```

**可透過 Web UI 管理**：Ctrl+K → Directives

### 優先順序

使用者目錄 (`~/.adjutant/prompts/directives/`) 的同名檔案會覆蓋內建版本。

---

## RAG 搜尋

### 索引原理

```
notebook/*.md
      │
      ▼ chunk_markdown()
  按 ## 標題切塊（~500 tokens/塊）
      │
      ▼ embed()
  Ollama nomic-embed-text 或 sentence-transformers
      │
      ▼ LanceDB
  儲存向量 + metadata（source, heading, chunk_idx）
```

### 搜尋原理

```
查詢: "API 設計原則"
      │
      ▼ embed()
  查詢轉為向量
      │
      ▼ LanceDB.search()
  餘弦相似度 → top-k 結果
      │
      ▼ format_rag_context()
  "## 相關筆記
   ### notes/api-design.md > 設計原則
   ..."
```

### 增量更新

索引追蹤每個檔案的 mtime。`adjutant index build` 只重新處理修改過的檔案。要強制全部重建，刪除 `~/.adjutant/index/` 後再 build。

---

## MCP Server

讓 Claude Code、Cursor 等 AI 程式設計工具直接呼叫 Adjutant 的能力。

### 設定

**Claude Code — `.mcp.json`：**
```json
{
  "mcpServers": {
    "adjutant": {
      "command": "/path/to/.venv/bin/adjutant",
      "args": ["mcp"]
    }
  }
}
```

> 注意：`command` 要用 venv 內的完整路徑，或確保 adjutant 在 PATH 中。

### 使用情境

```
你在 Claude Code 裡寫程式：

> "查一下我筆記裡關於 auth middleware 的記錄"
  → Claude Code 呼叫 search_notes("auth middleware")
  → 回傳相關筆記段落

> "把這個 bug 加到 inbox"
  → Claude Code 呼叫 capture_inbox("auth middleware race condition bug")

> "跑一下 inbox triage"
  → Claude Code 呼叫 run_sop("inbox-triage")
  → 回傳完整的分類建議 prompt
```

### 工具一覽

| 工具 | 說明 | 需要索引 |
|------|------|---------|
| `read_note` | 讀筆記檔案 | 否 |
| `list_notes` | 列出目錄 | 否 |
| `capture_inbox` | 加到 inbox | 否 |
| `get_stats` | 筆記統計 | 否 |
| `search_notes` | 語意搜尋 | **是** |
| `search_memory` | 搜尋記憶 | **是** |
| `add_memory` | 新增記憶 | **是** |
| `list_sops` | SOP 列表 | 否 |
| `run_sop` | 執行 SOP | 否 |

---

## Telegram Bot

### 訊息路由邏輯

```
Telegram 訊息進來
        │
        ▼
  是指令？ (/start, /inbox, /tasks)
   │Y            │N
   ▼              ▼
 回應指令     AI 判斷意圖
              │
              ├── 是問題 → AI 回答（用 persona + memory + RAG）
              │
              └── 是筆記 → 加到 inbox.md + 回覆確認
                     │
                     ▼ 失敗時
                  fallback → 一律加到 inbox
```

### Bot ↔ Web UI 同步

Bot 的所有對話會即時廣播到 Web UI 的 terminal feed（透過 WebSocket broadcast）。你可以在 Web UI 看到手機上的對話。

---

## 檔案結構總覽

```
~/.adjutant/                          # 使用者資料目錄
├── config.toml                       # 主要設定
├── persona.md                        # 人格設定（舊位置，向下相容）
├── memory.md                         # 平文字記憶
├── .bot_token                        # Telegram token（chmod 0600）
├── sessions/                         # 對話歷史（JSON）
├── sop/                              # 使用者自訂 SOP
├── index/                            # LanceDB 向量索引
│   ├── notebook_chunks.lance/        # RAG 筆記索引
│   ├── memories.lance/               # 向量記憶
│   └── _meta.json                    # 索引 metadata
└── prompts/
    ├── persona.md                    # 人格設定（新位置）
    └── directives/                   # 自訂觸發指令
        └── my_directive.md

~/YourNotebook/                       # 筆記本（你的筆記資料夾）
├── inbox.md                          # 收件匣
├── tasks.md                          # 任務追蹤
├── journal/daily/                    # 每日日誌
│   ├── 2026-03-24.md
│   └── 2026-03-25.md
├── projects/                         # 專案
├── notes/                            # 知識筆記
└── assets/                           # 圖片附件
```

---

## 故障排除

### 索引搜尋不到東西
```bash
adjutant index status    # 確認索引已建立
adjutant index build     # 重建索引
```

### Embedding provider 不可用
- Ollama：確認 `ollama serve` 在跑，且 `ollama pull nomic-embed-text` 已拉
- sentence-transformers：`pip install -e ".[local-embeddings]"`

### Ollama 連不上
- 檢查 `~/.adjutant/config.toml` 的 `ollama_base_url`
- 預設是 `http://localhost:11434`，遠端 Ollama 需改成對應 URL

### Web UI 打不開
```bash
source .venv/bin/activate    # 確認在 venv 裡
adjutant web                  # 預設 8100 port
```

### Bot 啟動失敗
- 確認 token：`cat ~/.adjutant/.bot_token`
- 確認沒有其他 instance 在跑同一個 token

### SOP 沒有提示輸入參數
- 確認 SOP 有 `version: "2"` 和 `inputs:` 欄位
- Web UI 才會彈出參數視窗；v1 格式不支援 inputs

### 記憶沒有生效
- 向量記憶需要 embedding provider
- 確認 `adjutant memory list` 有內容
- `adjutant memory search "query"` 測試檢索
