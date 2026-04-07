"""LLM Wiki — persistent, LLM-maintained knowledge base over notebook sources.

The wiki sits between raw notebook sources and the user. Instead of re-deriving
knowledge from scratch on every query (like RAG), the LLM incrementally builds
and maintains a structured wiki of summaries, entities, concepts, and comparisons.

Operations:
  - init:   create wiki directory structure and schema
  - ingest: process a source document into wiki pages
  - query:  two-pass retrieval (index.md → pages → answer)
  - lint:   health-check the wiki for contradictions, orphans, etc.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from adjutant.core.chat import chat_once, get_persona
from adjutant.core.dispatcher import Dispatcher
from adjutant.core.file_ops import read_file, resolve_safe, write_file

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Wiki subdirectories created on init
_WIKI_DIRS = ["summaries", "entities", "concepts", "comparisons"]

# Max chars of index.md to inject as context in regular chat
_INDEX_CONTEXT_LIMIT = 8000


def _load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    path = _PROMPTS_DIR / f"{name}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt template not found: {path}")


@dataclass
class IngestResult:
    """Result of an ingest operation."""

    source_path: str
    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class WikiStatus:
    """Wiki health status."""

    exists: bool = False
    page_count: int = 0
    last_log_entry: str = ""
    categories: dict[str, int] = field(default_factory=dict)


class WikiManager:
    """Manages the LLM Wiki lifecycle: init, ingest, query, lint."""

    def __init__(
        self,
        wiki_root: Path,
        notebook_root: Path,
        dispatcher: Dispatcher,
        ai_tool: str = "claude",
        model: str | None = None,
    ):
        self._wiki_root = wiki_root
        self._notebook_root = notebook_root
        self._dispatcher = dispatcher
        self._ai_tool = ai_tool
        self._model = model

    # ── Structure ──────────────────────────────────────────

    @property
    def wiki_root(self) -> Path:
        return self._wiki_root

    def wiki_exists(self) -> bool:
        """Check if the wiki has been initialized."""
        return (self._wiki_root / "index.md").is_file()

    async def init_wiki(self) -> None:
        """Create wiki directory structure with schema, index, and log."""
        self._wiki_root.mkdir(parents=True, exist_ok=True)
        for subdir in _WIKI_DIRS:
            (self._wiki_root / subdir).mkdir(exist_ok=True)

        # Copy schema template
        schema_src = _PROMPTS_DIR / "wiki_schema.md"
        schema_dst = self._wiki_root / "_schema.md"
        if not schema_dst.is_file():
            shutil.copy2(schema_src, schema_dst)

        # Create empty index
        index_path = self._wiki_root / "index.md"
        if not index_path.is_file():
            index_path.write_text(
                "# Wiki 索引\n\n"
                "## 摘要\n"
                "| 頁面 | 來源 | 摘要 | 更新日期 |\n"
                "|------|------|------|----------|\n\n"
                "## 實體\n"
                "| 頁面 | 類型 | 摘要 | 相關來源 |\n"
                "|------|------|------|----------|\n\n"
                "## 概念\n"
                "| 頁面 | 摘要 | 相關來源 |\n"
                "|------|------|----------|\n\n"
                "## 比較\n"
                "| 頁面 | 摘要 | 更新日期 |\n"
                "|------|------|----------|\n",
                encoding="utf-8",
            )

        # Create empty log
        log_path = self._wiki_root / "log.md"
        if not log_path.is_file():
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            log_path.write_text(
                f"# Wiki 操作日誌\n\n"
                f"## [{now}] init | Wiki 初始化\n\n"
                f"- 建立目錄結構：{', '.join(_WIKI_DIRS)}\n"
                f"- 建立 _schema.md, index.md, log.md\n",
                encoding="utf-8",
            )

    def get_schema(self) -> str:
        """Read wiki/_schema.md."""
        path = self._wiki_root / "_schema.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return ""

    def get_index(self) -> str:
        """Read wiki/index.md."""
        path = self._wiki_root / "index.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return ""

    # ── Page management ────────────────────────────────────

    def read_page(self, rel_path: str) -> str:
        """Read a wiki page by relative path (e.g. 'entities/python.md')."""
        return read_file(self._wiki_root / rel_path, self._wiki_root)

    def write_page(self, rel_path: str, content: str) -> None:
        """Write a wiki page by relative path."""
        write_file(self._wiki_root / rel_path, content, self._wiki_root)

    def list_pages(self) -> list[str]:
        """List all wiki pages (relative paths), excluding special files."""
        special = {"_schema.md", "index.md", "log.md"}
        pages: list[str] = []
        for path in sorted(self._wiki_root.rglob("*.md")):
            rel = str(path.relative_to(self._wiki_root))
            if rel not in special:
                pages.append(rel)
        return pages

    def append_log(self, entry: str) -> None:
        """Append an entry to wiki/log.md."""
        log_path = self._wiki_root / "log.md"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{entry}\n")

    def get_status(self) -> WikiStatus:
        """Get wiki status summary."""
        if not self.wiki_exists():
            return WikiStatus(exists=False)

        pages = self.list_pages()
        categories: dict[str, int] = {}
        for p in pages:
            cat = p.split("/")[0] if "/" in p else "root"
            categories[cat] = categories.get(cat, 0) + 1

        last_log = ""
        log_path = self._wiki_root / "log.md"
        if log_path.is_file():
            text = log_path.read_text(encoding="utf-8")
            # Find last ## entry
            entries = re.findall(r"^## \[.+$", text, re.MULTILINE)
            if entries:
                last_log = entries[-1]

        return WikiStatus(
            exists=True,
            page_count=len(pages),
            last_log_entry=last_log,
            categories=categories,
        )

    # ── Ingest ─────────────────────────────────────────────

    async def ingest(self, source_path: Path) -> IngestResult:
        """Ingest a source document into the wiki.

        Reads the source, sends it to the LLM with wiki schema and index,
        parses the structured JSON response, and writes wiki pages.
        """
        result = IngestResult(source_path=str(source_path))

        # Read source
        try:
            source_content = read_file(source_path, self._notebook_root)
        except Exception as e:
            result.errors.append(f"Failed to read source: {e}")
            return result

        # Build ingest prompt
        template = _load_prompt_template("wiki_ingest")
        rel_path = str(source_path.relative_to(self._notebook_root))
        prompt = template.format(
            schema=self.get_schema(),
            index=self.get_index(),
            source_path=rel_path,
            source_content=source_content,
        )

        # Call LLM
        response = await chat_once(
            self._dispatcher,
            prompt,
            self._notebook_root,
            ai_tool=self._ai_tool,
            model=self._model,
            timeout=300,
        )

        # Parse JSON from response
        plan = self._parse_ingest_response(response)
        if plan is None:
            result.errors.append("Failed to parse LLM response as JSON")
            logger.warning("Raw LLM response:\n%s", response[:2000])
            return result

        # Execute plan: write pages
        for page in plan.get("pages", []):
            page_path = page.get("path", "")
            content = page.get("content", "")
            action = page.get("action", "create")
            if not page_path or not content:
                continue
            try:
                self.write_page(page_path, content)
                if action == "create":
                    result.pages_created.append(page_path)
                else:
                    result.pages_updated.append(page_path)
            except Exception as e:
                result.errors.append(f"Failed to write {page_path}: {e}")

        # Update index.md
        index_updates = plan.get("index_updates", [])
        if index_updates:
            self._apply_index_updates(index_updates)

        # Append log
        log_entry = plan.get("log_entry", "")
        if log_entry:
            self.append_log(log_entry)
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            created = ", ".join(result.pages_created) or "none"
            updated = ", ".join(result.pages_updated) or "none"
            self.append_log(
                f"## [{now}] ingest | {rel_path}\n\n"
                f"- 建立頁面：{created}\n"
                f"- 更新頁面：{updated}\n"
            )

        return result

    def _parse_ingest_response(self, response: str) -> dict | None:
        """Extract JSON plan from LLM response."""
        # Try to find JSON block in markdown code fence
        match = re.search(r"```json\s*\n(.*?)\n```", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try raw JSON
        # Find first { and last }
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(response[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _apply_index_updates(self, updates: list[dict]) -> None:
        """Append new rows to index.md sections."""
        index_path = self._wiki_root / "index.md"
        content = index_path.read_text(encoding="utf-8")

        # Map section names to their Chinese headers
        section_map = {
            "summaries": "## 摘要",
            "entities": "## 實體",
            "concepts": "## 概念",
            "comparisons": "## 比較",
        }

        for update in updates:
            section = update.get("section", "")
            row = update.get("row", "")
            if not section or not row:
                continue

            header = section_map.get(section)
            if not header:
                continue

            # Find the section and its table, append row before next section
            # Strategy: find the header, then find the next ## or end of file,
            # insert the row just before that boundary
            pattern = re.escape(header) + r".*?\n"
            idx = content.find(header)
            if idx == -1:
                continue

            # Find end of the table (next ## heading or EOF)
            next_section = content.find("\n## ", idx + len(header))
            if next_section == -1:
                # Append at end
                content = content.rstrip() + "\n" + row + "\n"
            else:
                # Insert before next section
                content = (
                    content[:next_section].rstrip()
                    + "\n"
                    + row
                    + "\n"
                    + content[next_section:]
                )

        index_path.write_text(content, encoding="utf-8")

    # ── Query ──────────────────────────────────────────────

    async def query(self, question: str) -> str:
        """Two-pass wiki query: index.md → relevant pages → synthesized answer."""
        if not self.wiki_exists():
            return "Wiki 尚未初始化。請先執行 `adjutant wiki init`。"

        index_content = self.get_index()

        # Pass 1: Ask LLM which pages are relevant
        pass1_prompt = (
            f"{get_persona()}\n\n"
            f"## Wiki 索引\n\n{index_content}\n\n"
            f"## 任務\n\n"
            f"根據以上 wiki 索引，指揮官想知道：{question}\n\n"
            f"請列出最相關的 wiki 頁面路徑（最多 10 個），每行一個，不要其他文字。\n"
            f"如果沒有相關頁面，只輸出「無相關頁面」。"
        )

        pass1_response = await chat_once(
            self._dispatcher,
            pass1_prompt,
            self._notebook_root,
            ai_tool=self._ai_tool,
            model=self._model,
            timeout=60,
        )

        if "無相關頁面" in pass1_response:
            return f"Wiki 中沒有找到與「{question}」相關的頁面。可以嘗試 ingest 更多來源。"

        # Parse page paths from response
        page_paths = self._parse_page_paths(pass1_response)
        if not page_paths:
            return f"Wiki 中沒有找到與「{question}」相關的頁面。"

        # Read relevant pages
        page_contents: list[str] = []
        for p in page_paths:
            try:
                content = self.read_page(p)
                page_contents.append(f"### {p}\n\n{content}")
            except (FileNotFoundError, Exception):
                continue

        if not page_contents:
            return "找到了相關頁面但無法讀取。請檢查 wiki 完整性。"

        # Pass 2: Synthesize answer from pages
        pages_text = "\n\n---\n\n".join(page_contents)
        pass2_prompt = (
            f"{get_persona()}\n\n"
            f"## 相關 Wiki 頁面\n\n{pages_text}\n\n"
            f"## 當前請求\n\n"
            f"[User]: {question}\n\n"
            f"請根據以上 wiki 頁面內容回答指揮官的問題。引用具體頁面作為依據。"
        )

        return await chat_once(
            self._dispatcher,
            pass2_prompt,
            self._notebook_root,
            ai_tool=self._ai_tool,
            model=self._model,
            timeout=120,
        )

    def _parse_page_paths(self, response: str) -> list[str]:
        """Extract page paths from LLM response."""
        paths: list[str] = []
        for line in response.strip().splitlines():
            line = line.strip().lstrip("- ").strip()
            # Remove markdown link syntax [text](path) → path
            link_match = re.match(r"\[.*?\]\((.+?)\)", line)
            if link_match:
                line = link_match.group(1)
            # Must look like a relative path ending in .md
            if line.endswith(".md") and "/" in line and not line.startswith("/"):
                paths.append(line)
        return paths[:10]

    def get_wiki_context_for_chat(self) -> str | None:
        """Get truncated wiki index for injection into regular chat prompts.

        Returns None if wiki doesn't exist or is empty.
        """
        if not self.wiki_exists():
            return None

        index_content = self.get_index()
        if not index_content.strip():
            return None

        # Truncate if too long
        if len(index_content) > _INDEX_CONTEXT_LIMIT:
            index_content = index_content[:_INDEX_CONTEXT_LIMIT] + "\n\n... (索引已截斷)"

        return f"## Wiki 知識庫索引\n\n{index_content}"

    # ── Lint ───────────────────────────────────────────────

    async def lint(self) -> str:
        """Run a health check on the wiki."""
        if not self.wiki_exists():
            return "Wiki 尚未初始化。請先執行 `adjutant wiki init`。"

        # Gather all wiki content
        pages = self.list_pages()
        if not pages:
            return "Wiki 是空的。請先 ingest 一些來源文件。"

        index_content = self.get_index()

        # Build page summaries (first 500 chars each to stay within limits)
        page_summaries: list[str] = []
        for p in pages:
            try:
                content = self.read_page(p)
                preview = content[:500]
                if len(content) > 500:
                    preview += "..."
                page_summaries.append(f"### {p}\n{preview}")
            except Exception:
                page_summaries.append(f"### {p}\n(無法讀取)")

        pages_text = "\n\n".join(page_summaries)

        prompt = (
            f"{get_persona()}\n\n"
            f"## Wiki Lint — 健康檢查\n\n"
            f"### 索引\n\n{index_content}\n\n"
            f"### 頁面概覽（{len(pages)} 頁）\n\n{pages_text}\n\n"
            f"## 任務\n\n"
            f"請檢查這個 wiki 的健康狀態，報告以下問題：\n\n"
            f"1. **矛盾**：不同頁面對同一事實的描述不一致\n"
            f"2. **孤立頁面**：未被 index.md 收錄的頁面\n"
            f"3. **缺失頁面**：index.md 中引用但不存在的頁面\n"
            f"4. **缺少交叉引用**：應該互相連結但沒有的頁面\n"
            f"5. **資料缺口**：被提及但缺少獨立頁面的重要概念或實體\n"
            f"6. **改善建議**：其他可以強化 wiki 的建議\n\n"
            f"以結構化的報告格式輸出。"
        )

        return await chat_once(
            self._dispatcher,
            prompt,
            self._notebook_root,
            ai_tool=self._ai_tool,
            model=self._model,
            timeout=180,
        )
