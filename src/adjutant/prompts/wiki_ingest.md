你是 Adjutant Wiki 維護者。請消化以下來源文件，並產出 wiki 更新計畫。

## Wiki 規範

{schema}

## 目前 Wiki 索引

{index}

## 來源文件

### {source_path}

{source_content}

## 指示

請分析來源文件，產出 JSON 格式的更新計畫。你必須：

1. **建立摘要頁**：為來源建立一個 summaries/ 頁面
2. **辨識實體與概念**：找出重要的人、工具、專案、方法論等
3. **建立或更新頁面**：為每個重要實體/概念建立新頁面，或更新已存在的頁面
4. **交叉引用**：在相關頁面之間建立連結
5. **更新索引**：為每個新頁面或更新的頁面提供 index.md 條目

請嚴格輸出以下 JSON 格式（不要加任何其他文字）：

```json
{
  "pages": [
    {
      "path": "summaries/source-name.md",
      "action": "create",
      "content": "---\ntype: summary\nsources:\n  - original/path.md\ncreated: YYYY-MM-DD\nupdated: YYYY-MM-DD\ntags: [tag1]\n---\n\n頁面內容..."
    },
    {
      "path": "entities/entity-name.md",
      "action": "create",
      "content": "..."
    }
  ],
  "index_updates": [
    {
      "section": "summaries",
      "row": "| [source-name.md](summaries/source-name.md) | original/path.md | 摘要文字 | YYYY-MM-DD |"
    }
  ],
  "log_entry": "## [YYYY-MM-DD HH:MM] ingest | 來源描述\n\n- 建立頁面：...\n- 更新頁面：...\n- 影響範圍：..."
}
```

對於需要更新的已存在頁面（action: "update"），content 欄位應包含完整的更新後頁面內容（不是差異）。
