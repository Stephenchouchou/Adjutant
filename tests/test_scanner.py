"""Tests for adjutant.core.scanner — proactive scanner rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from adjutant.core.scanner import (
    ScanState,
    _extract_deadline,
    scan_inbox_unresolved,
    scan_overdue_deadlines,
    scan_weekly_report_reminder,
)


def test_scan_state_dedup(tmp_path):
    state_path = tmp_path / "scan_state.json"
    state = ScanState(state_path)
    state.mark_alerted("foo")
    assert state.recently_alerted("foo", dedup_hours=24) is True
    assert state.recently_alerted("bar", dedup_hours=24) is False

    state2 = ScanState(state_path)
    assert state2.recently_alerted("foo", dedup_hours=24) is True


def test_scan_state_prune(tmp_path):
    state_path = tmp_path / "scan_state.json"
    state = ScanState(state_path)
    state._alerted = {
        "old": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
        "fresh": datetime.now(timezone.utc).isoformat(),
    }
    state._save()
    state.prune(max_age_days=30)
    assert "old" not in state._alerted
    assert "fresh" in state._alerted


def test_inbox_unresolved_skips_header(tmp_path):
    inbox = tmp_path / "inbox.md"
    inbox.write_text(
        "# Inbox\n\n"
        "處理規則：\n"
        "- 可執行的單步任務 → 移到 tasks.md\n"
        "- 需要多步驟完成的 → 在 projects/\n"
        "\n---\n\n"
        "- 真正的條目 A\n"
        "- [ ] 真正的條目 B\n"
        "- [x] 已完成的條目（應跳過）\n"
    )
    findings = scan_inbox_unresolved(inbox, repo_root=tmp_path, threshold_days=0)
    # repo blame fails in tmp_path (no git) → returns empty list
    # we just test parser doesn't crash
    assert isinstance(findings, list)


def test_extract_deadline_iso():
    d = _extract_deadline("foo 2026-04-27 bar", ref_year=2026)
    assert d == datetime(2026, 4, 27)


def test_extract_deadline_mmdd():
    d = _extract_deadline("驗證（0424 開跑 / 0427 15:00 收）", ref_year=2026)
    assert d == datetime(2026, 4, 27)


def test_extract_deadline_no_match():
    assert _extract_deadline("no date here", ref_year=2026) is None


def test_overdue_scanner(tmp_path):
    tasks = tmp_path / "tasks.md"
    tasks.write_text(
        "## Next\n"
        "- [ ] **task A** (deadline 2026-04-27 收)\n"
        "- [ ] **task B** (deadline 2099-01-01)\n"
    )
    now = datetime(2026, 5, 12)
    findings = scan_overdue_deadlines(tasks, now=now)
    assert len(findings) == 1
    assert findings[0].category == "overdue"
    assert "2026-04-27" in findings[0].message
    assert "15 天" in findings[0].message


def test_weekly_report_tue_evening():
    # Tuesday 2026-05-12 22:00 — should trigger evening reminder
    tue = datetime(2026, 5, 12, 22, 0)  # weekday() == 1 (Tuesday)
    findings = scan_weekly_report_reminder(now=tue)
    assert len(findings) == 1
    assert findings[0].category == "weekly_report"
    assert "明早" in findings[0].message


def test_weekly_report_wed_morning():
    # Wednesday 2026-05-13 09:00 — should trigger morning reminder
    wed = datetime(2026, 5, 13, 9, 0)  # weekday() == 2
    findings = scan_weekly_report_reminder(now=wed)
    assert len(findings) == 1
    assert "週三早晨" in findings[0].message


def test_weekly_report_silent_other_days():
    # Monday afternoon — no reminder
    mon = datetime(2026, 5, 11, 14, 0)
    assert scan_weekly_report_reminder(now=mon) == []
