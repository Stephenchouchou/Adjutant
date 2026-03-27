# 2026-03-27 — Reminder System, Session Continuity, Web Daemon Mode

## Changes

### Reminder / Alarm System (new)
- New `src/adjutant/core/reminders.py`: Reminder model, JSON-backed ReminderStore, asyncio ReminderScheduler
- Time parsing helper `parse_reminder_time()` in `bot/handlers.py`: relative (5m, 1h, 30s) and absolute (HH:MM, YYYY-MM-DD HH:MM)
- Telegram bot commands: `/remind <time> <text>`, `/reminders`, `/cancel <id>`
- REST APIs: `GET/POST/DELETE /api/reminders`
- Scheduler auto-starts with web server, queues reminders if bot offline, flushes on bot connect
- Web UI: HUD stat block (⏰ REMIND), modal for creating/viewing/cancelling reminders

### Web Session Continuity
- Frontend stores session ID in localStorage, auto-resumes on WebSocket reconnect
- New `resume_session` WebSocket message type for seamless restore
- Server includes `session_id` in init message
- Periodic `session.save()` after each AI response (crash safety)

### Web Daemon Mode
- `adjutant web` now runs in background by default, terminal returns immediately
- `adjutant web --fg` for foreground mode
- `adjutant web --stop` to stop background server
- PID file at `~/.adjutant/web.pid`, logs at `~/.adjutant/web.log`
- Health check before opening browser to avoid OFFLINE state

### Bot Auto-Start & Settings
- Bot auto-starts on web server launch if token exists (no manual START needed)
- Bot token field added to Settings modal for reconfiguration
- `/api/settings` now returns `has_token` flag

## Files Modified
- `src/adjutant/config.py` — added REMINDERS_PATH
- `src/adjutant/core/reminders.py` — new file
- `src/adjutant/bot/handlers.py` — parse_reminder_time()
- `src/adjutant/bot/telegram.py` — /remind, /reminders, /cancel, scheduler integration
- `src/adjutant/web/server.py` — reminder APIs, scheduler lifecycle, session resume, bot auto-start
- `src/adjutant/web/static/index.html` — reminder stat block, reminder modal, bot token in settings
- `src/adjutant/web/static/style.css` — reminder styles
- `src/adjutant/web/static/app.js` — reminder UI, session localStorage, bot token in settings
- `src/adjutant/__main__.py` — web daemon mode (background/fg/stop)
