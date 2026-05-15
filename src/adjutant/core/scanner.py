"""Proactive scanner — scan inbox/tasks/daily for anomalies and push alerts."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

from adjutant.config import CONFIG_DIR, AdjutantConfig

logger = logging.getLogger(__name__)

SendFn = Callable[[int, str], Awaitable[None]]

SCAN_STATE_PATH = CONFIG_DIR / "scan_state.json"
DEFAULT_ALERT_DEDUP_HOURS = 24
DEFAULT_INTERVAL_SECONDS = 60 * 60  # hourly


@dataclass
class ScanFinding:
    """A single anomaly worth alerting the commander about."""

    key: str  # stable id for dedup (e.g. "stuck:<line-hash>")
    category: str  # stuck_task | inbox_unresolved | weekly_report | overdue
    message: str  # user-facing alert body


class ScanState:
    """JSON-backed dedup store — remembers which findings have been alerted."""

    def __init__(self, path: Path = SCAN_STATE_PATH):
        self._path = path
        self._alerted: dict[str, str] = {}  # key -> ISO8601 alert time
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._alerted = data.get("alerted", {})
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("scan_state load failed: %s", e)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"alerted": self._alerted}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def recently_alerted(self, key: str, dedup_hours: int) -> bool:
        ts = self._alerted.get(key)
        if not ts:
            return False
        try:
            last = datetime.fromisoformat(ts)
        except ValueError:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last < timedelta(hours=dedup_hours)

    def mark_alerted(self, key: str) -> None:
        self._alerted[key] = datetime.now(timezone.utc).isoformat()
        self._save()

    def prune(self, max_age_days: int = 30) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        keep = {}
        for k, ts in self._alerted.items():
            try:
                last = datetime.fromisoformat(ts)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if last > cutoff:
                    keep[k] = ts
            except ValueError:
                continue
        if len(keep) != len(self._alerted):
            self._alerted = keep
            self._save()


def _git_line_age_days(file_path: Path, line_number: int, repo_root: Path) -> int | None:
    """Return the age in days of a specific line via git blame, or None on failure."""
    try:
        rel = file_path.relative_to(repo_root)
    except ValueError:
        return None
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "blame",
                "-L",
                f"{line_number},{line_number}",
                "--porcelain",
                str(rel),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if line.startswith("author-time "):
                ts = int(line.split()[1])
                age = datetime.now(timezone.utc) - datetime.fromtimestamp(ts, tz=timezone.utc)
                return age.days
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    return None


def _find_repo_root(path: Path) -> Path | None:
    p = path.resolve()
    for parent in (p, *p.parents):
        if (parent / ".git").exists():
            return parent
    return None


# ── Scan rules ─────────────────────────────────────────────


def scan_stuck_tasks(
    tasks_path: Path,
    repo_root: Path,
    threshold_days: int = 7,
) -> list[ScanFinding]:
    """Find tasks.md `- [ ]` items unchanged for ≥threshold_days."""
    findings: list[ScanFinding] = []
    if not tasks_path.is_file():
        return findings

    item_re = re.compile(r"^\s*- \[ \]\s+(.+)$")
    lines = tasks_path.read_text(encoding="utf-8").splitlines()
    for idx, raw in enumerate(lines, start=1):
        m = item_re.match(raw)
        if not m:
            continue
        text = m.group(1).strip()
        age = _git_line_age_days(tasks_path, idx, repo_root)
        if age is None or age < threshold_days:
            continue
        key = f"stuck:{tasks_path.name}:{idx}:{age // 7}w"
        findings.append(
            ScanFinding(
                key=key,
                category="stuck_task",
                message=(
                    f"⚠️ Stuck task ({age} 天未動)：\n"
                    f"  {text[:120]}"
                ),
            )
        )
    return findings


def scan_inbox_unresolved(
    inbox_path: Path,
    repo_root: Path,
    threshold_days: int = 3,
) -> list[ScanFinding]:
    """Find inbox.md unchecked `- [ ]` items older than threshold_days."""
    findings: list[ScanFinding] = []
    if not inbox_path.is_file():
        return findings

    # Match BOTH `- [ ] ...` and `- ...` (inbox uses both formats).
    unchecked_re = re.compile(r"^\s*- (?:\[ \] )?(?!\[x\])(.+)$")
    lines = inbox_path.read_text(encoding="utf-8").splitlines()

    # Skip the header instructions: real entries live after the first `---`.
    body_start = 0
    for i, raw in enumerate(lines):
        if raw.strip() == "---":
            body_start = i + 1
            break

    for idx, raw in enumerate(lines[body_start:], start=body_start + 1):
        m = unchecked_re.match(raw)
        if not m:
            continue
        text = m.group(1).strip()
        # Skip empty bullets and section dividers
        if not text or text.startswith("---"):
            continue
        age = _git_line_age_days(inbox_path, idx, repo_root)
        if age is None or age < threshold_days:
            continue
        key = f"inbox:{idx}:{age // 3}d"  # re-alert every 3-day bucket
        findings.append(
            ScanFinding(
                key=key,
                category="inbox_unresolved",
                message=(
                    f"📥 Inbox 未歸檔 ({age} 天)：\n"
                    f"  {text[:120]}"
                ),
            )
        )
    return findings


def scan_weekly_report_reminder(
    now: datetime | None = None,
) -> list[ScanFinding]:
    """Trigger weekly-report reminder Tue 21:00 / Wed 08:00 local time."""
    now = now or datetime.now()
    # weekday(): Mon=0 ... Sun=6
    # Tuesday evening (21:00+) or Wednesday morning (08:00–11:00)
    iso_week = now.isocalendar()
    key_base = f"weekly:{iso_week.year}-W{iso_week.week:02d}"

    if now.weekday() == 1 and now.hour >= 21:
        return [
            ScanFinding(
                key=f"{key_base}:tue",
                category="weekly_report",
                message=(
                    "📊 週報前夜提醒：\n"
                    "  明早彙整本週 daily notes → 週三產出週報。\n"
                    "  記得比對上週 Backlog/This Week，找無聲消失項目。"
                ),
            )
        ]
    if now.weekday() == 2 and 8 <= now.hour < 11:
        return [
            ScanFinding(
                key=f"{key_base}:wed",
                category="weekly_report",
                message=(
                    "📊 週三早晨：今日為週報截止日。\n"
                    "  副官待命接收 `/週報` 指令。"
                ),
            )
        ]
    return []


_DATE_PATTERNS = (
    # 2026-04-27 / 2026/04/27
    re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
    # 0427、0427 15:00 收
    re.compile(r"(?<!\d)(0[1-9]|1[0-2])(\d{2})(?:\s+\d{1,2}:\d{2})?\s*收"),
)


def _extract_deadline(text: str, ref_year: int) -> datetime | None:
    """Best-effort deadline extraction. Returns naive datetime (date only)."""
    m = _DATE_PATTERNS[0].search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _DATE_PATTERNS[1].search(text)
    if m:
        try:
            return datetime(ref_year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def scan_overdue_deadlines(
    tasks_path: Path,
    now: datetime | None = None,
) -> list[ScanFinding]:
    """Find `- [ ]` tasks whose embedded deadline has passed."""
    findings: list[ScanFinding] = []
    if not tasks_path.is_file():
        return findings
    now = now or datetime.now()

    item_re = re.compile(r"^\s*- \[ \]\s+(.+)$")
    lines = tasks_path.read_text(encoding="utf-8").splitlines()
    for idx, raw in enumerate(lines, start=1):
        m = item_re.match(raw)
        if not m:
            continue
        text = m.group(1).strip()
        deadline = _extract_deadline(text, now.year)
        if not deadline:
            continue
        if deadline.date() >= now.date():
            continue
        days_overdue = (now.date() - deadline.date()).days
        key = f"overdue:{idx}:{deadline.date().isoformat()}"
        findings.append(
            ScanFinding(
                key=key,
                category="overdue",
                message=(
                    f"⏰ 過期 {days_overdue} 天 (deadline {deadline.date()})：\n"
                    f"  {text[:120]}"
                ),
            )
        )
    return findings


# ── Scanner ──────────────────────────────────────────────


class ProactiveScanner:
    """Periodically scan notebook for anomalies and push alerts via send_fn."""

    def __init__(
        self,
        config: AdjutantConfig,
        send_fn: SendFn | None,
        get_chat_ids: Callable[[], list[int]],
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        dedup_hours: int = DEFAULT_ALERT_DEDUP_HOURS,
    ):
        self._config = config
        self._send_fn = send_fn
        self._get_chat_ids = get_chat_ids
        self._interval = interval_seconds
        self._dedup_hours = dedup_hours
        self._state = ScanState()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_findings: list[ScanFinding] = []

    @property
    def last_findings(self) -> list[ScanFinding]:
        return list(self._last_findings)

    def collect_findings(self) -> list[ScanFinding]:
        """Run all scan rules once. Pure function — no side effects."""
        root = self._config.notebook_root
        tasks_path = root / self._config.paths.tasks
        inbox_path = root / self._config.paths.inbox
        repo_root = _find_repo_root(tasks_path) or root

        findings: list[ScanFinding] = []
        findings.extend(scan_stuck_tasks(tasks_path, repo_root))
        findings.extend(scan_inbox_unresolved(inbox_path, repo_root))
        findings.extend(scan_weekly_report_reminder())
        findings.extend(scan_overdue_deadlines(tasks_path))
        return findings

    async def scan_once(self) -> int:
        """Run one scan pass, push alerts for new findings. Returns alerts sent."""
        self._state.prune()
        findings = self.collect_findings()
        self._last_findings = findings

        # Group new findings by category for a single digested alert per scan
        new_by_cat: dict[str, list[ScanFinding]] = {}
        for f in findings:
            if self._state.recently_alerted(f.key, self._dedup_hours):
                continue
            new_by_cat.setdefault(f.category, []).append(f)

        if not new_by_cat:
            return 0

        chat_ids = self._get_chat_ids() or []
        if not chat_ids or self._send_fn is None:
            logger.info(
                "ProactiveScanner: %d new findings but no chat_ids/send_fn — skipping push",
                sum(len(v) for v in new_by_cat.values()),
            )
            # Still mark to avoid re-collecting endlessly in logs
            for items in new_by_cat.values():
                for f in items:
                    self._state.mark_alerted(f.key)
            return 0

        sent = 0
        for category, items in new_by_cat.items():
            body = "\n\n".join(f.message for f in items[:5])
            extra = f"\n\n（共 {len(items)} 項；僅顯示前 5 項）" if len(items) > 5 else ""
            msg = f"🛰️ 副官主動掃描 — {category}\n\n{body}{extra}"
            for chat_id in chat_ids:
                try:
                    await self._send_fn(chat_id, msg)
                    sent += 1
                except Exception as e:
                    logger.warning("ProactiveScanner push failed: %s", e)
                    continue
            for f in items:
                self._state.mark_alerted(f.key)
        return sent

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.scan_once()
            except Exception:
                logger.exception("ProactiveScanner scan_once error")
            await asyncio.sleep(self._interval)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("ProactiveScanner started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
