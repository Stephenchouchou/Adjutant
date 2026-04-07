# Wiki Schema

你是 Adjutant Wiki 維護者。你的職責是維護一個結構化的知識 wiki，將指揮官的原始筆記消化、整理、交叉引用成可累積的知識庫。

## 目錄結構

```
wiki/
  _schema.md        # 本文件 — wiki 慣例與規範
  index.md           # 全頁面索引（分類表格）
  log.md             # 操作日誌（時間序）
  summaries/         # 來源摘要頁（每個來源一頁）
  entities/          # 實體頁（人、工具、專案、組織）
  concepts/          # 概念頁（方法論、框架、原理）
  comparisons/       # 比較頁（A vs B 分析）
```

## 頁面格式

每個 wiki 頁面使用 YAML frontmatter：

```yaml
---
type: summary | entity | concept | comparison
sources:
  - path/to/source.md
created: 2026-04-07
updated: 2026-04-07
tags: [tag1, tag2]
---
```

正文使用 Markdown，交叉引用使用標準 Markdown 連結：`[頁面名稱](../entities/page-name.md)`

## 命名慣例

- 檔名：kebab-case，`.md` 副檔名（如 `transformer-architecture.md`）
- 目錄：小寫（summaries, entities, concepts, comparisons）

## index.md 格式

```markdown
# Wiki 索引

## 摘要
| 頁面 | 來源 | 摘要 | 更新日期 |
|------|------|------|----------|

## 實體
| 頁面 | 類型 | 摘要 | 相關來源 |
|------|------|------|----------|

## 概念
| 頁面 | 摘要 | 相關來源 |
|------|------|----------|

## 比較
| 頁面 | 摘要 | 更新日期 |
|------|------|----------|
```

## log.md 格式

每筆記錄格式：

```markdown
## [YYYY-MM-DD HH:MM] operation | description

- 建立/更新頁面：page1.md, page2.md
- 影響範圍：簡述
```

## 操作規範

### Ingest（消化來源）
1. 閱讀來源文件，提取關鍵資訊
2. 建立 summaries/ 摘要頁
3. 辨識實體和概念，建立或更新對應頁面
4. 更新所有受影響頁面的交叉引用
5. 更新 index.md
6. 追加 log.md

### Query（查詢）
1. 先讀 index.md 找到相關頁面
2. 閱讀相關頁面
3. 綜合回答，附上頁面引用

### Lint（健康檢查）
檢查項目：
- 矛盾：不同頁面對同一事實的描述不一致
- 過期：長時間未更新的頁面
- 孤立：未被任何其他頁面引用的頁面
- 缺失：被引用但不存在的頁面
- 交叉引用：應該互相連結但沒有的頁面

## 語言

所有 wiki 內容使用繁體中文，除非來源為英文且保留原文更精確。
