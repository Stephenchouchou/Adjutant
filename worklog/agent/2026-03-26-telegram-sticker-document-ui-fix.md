# 2026-03-26 Telegram sticker/document support, UI fix, timeout increase

## Changes

### Web UI: Commander message alignment fix
- Changed `.msg.commander` text-align from `right` to `left` in `style.css`
- Messages still float right (`align-self: flex-end`) but text content is now left-aligned for readability

### Telegram bot: Document & sticker capture
- Added `handle_document_capture()` and `handle_sticker_capture()` to `bot/handlers.py`
- Documents (PDF, etc.) are saved to `assets/` with original extension, linked in inbox as `[filename](path)`
- Stickers are saved as `.webp` to `assets/`, linked in inbox with emoji description
- Added `_on_document` and `_on_sticker` handlers in `telegram.py`, registered with `filters.Document.ALL` and `filters.Sticker.ALL`
- Both handlers broadcast to Web UI via WebSocket

### Telegram bot: Timeout increase
- Increased `chat_once` timeout from 60s to 300s to prevent "(response timed out)" on long inputs
