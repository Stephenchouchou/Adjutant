"""Adjutant chat — persona-aware conversational interface."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from adjutant.core.dispatcher import Dispatcher
from adjutant.models.session import Message, Session


ADJUTANT_PERSONA = """你是 Adjutant — 指揮官的個人知識管理副官。

## 你的角色

你是 StarCraft 中的副官（Adjutant）：接收指揮官的指令、掃描戰場資訊、產出情報摘要、提醒被遺忘的任務。你不替指揮官做決定，但提供可執行的建議。

## 核心職責

1. **分類歸檔** — 讀取 inbox，按意圖標籤分類到對應位置
2. **日報彙整** — 從 daily note 提取 Completed / Carry Forward / Insights
3. **週報生成** — 掃描近 7 天 daily notes，產出週報草稿
4. **任務掃描** — 檢查 tasks.md，找出 stale / blocked 項目並建議 next actions
5. **知識搜尋** — 回答關於指揮官筆記系統內容的問題
6. **主動提醒** — 發現過期 deadline、卡住的項目時主動告知

## 指揮官的筆記系統結構

- `inbox.md` — 收集箱（所有新東西先進這裡）
- `tasks.md` — 跨天任務追蹤
- `journal/daily/*.md` — 每日紀錄（Log + Experiment）
- `projects/*` — 專案狀態與實驗脈絡

這些是指揮官的 source of truth。你讀取、分析、建議，但不擅自修改。

## 人機分工原則

- **指揮官負責**：捕捉（inbox）、標記意圖、寫現場觀察（Log + Experiment）、優先級判斷
- **你負責**：分類歸檔、提取完成項、生成週報、關聯舊筆記、提醒卡住的任務

## 溝通風格

- 簡潔、直接、軍事化語調
- 用繁體中文回應（除非指揮官用其他語言）
- 主動提供可執行的建議，不只是摘要
- 稱呼使用者為「指揮官」
"""


def build_chat_prompt(
    user_prompt: str,
    session: Session,
    file_context: str | None = None,
) -> str:
    """Build a full prompt including persona, history, and optional file context."""
    parts: list[str] = [ADJUTANT_PERSONA]

    # Add conversation history (last 20 messages to keep prompt manageable)
    recent = session.messages[-20:]
    if recent:
        parts.append("\n## 先前對話紀錄\n")
        for msg in recent:
            role_label = "User" if msg.role == "user" else "Adjutant"
            content = msg.content
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            parts.append(f"[{role_label}]: {content}\n")

    # Add file context if provided
    if file_context:
        parts.append(f"\n## 參考檔案內容\n\n{file_context}\n")

    parts.append(f"\n## 當前請求\n\n[User]: {user_prompt}")

    return "\n".join(parts)


async def chat_stream(
    dispatcher: Dispatcher,
    prompt: str,
    work_dir: Path,
    ai_tool: str = "claude",
    model: str | None = None,
) -> AsyncIterator[str]:
    """Stream a chat response from the AI."""
    async for chunk in dispatcher.run(ai_tool, prompt, work_dir, model=model):
        yield chunk


async def chat_once(
    dispatcher: Dispatcher,
    prompt: str,
    work_dir: Path,
    ai_tool: str = "claude",
    model: str | None = None,
    timeout: float = 120,
) -> str:
    """Run a single chat and collect the full response."""
    parts: list[str] = []
    try:
        async def _collect():
            async for chunk in dispatcher.run(ai_tool, prompt, work_dir, model=model):
                parts.append(chunk)
        await asyncio.wait_for(_collect(), timeout=timeout)
    except asyncio.TimeoutError:
        if parts:
            return "".join(parts) + "\n\n(timeout)"
        return "(response timed out)"
    return "".join(parts)
