"""
Conftest: sets up environment and mocks *before* the bot module is imported.

Execution order matters:
  1. BOT_TOKEN must be in os.environ
  2. telegram / telegram.ext stubs must be in sys.modules
  3. telethon / telethon.sessions stubs must be in sys.modules
  4. sqlite3.connect must be patched to return a shared in-memory DB

All of these must happen before ``import ntn_mega_vouch_bot_polished``.
"""

import os
import sys
import sqlite3
from unittest.mock import MagicMock, patch

# ── 1. Environment ────────────────────────────────────────────────────────────
os.environ.setdefault("BOT_TOKEN", "test_token_for_unit_tests")

# ── 2. Stub out the telegram packages ─────────────────────────────────────────
# Build lightweight stubs so the module-level ``from telegram import …`` lines
# resolve without needing the real python-telegram-bot library installed.

_telegram_stub = MagicMock(name="telegram")
_telegram_ext_stub = MagicMock(name="telegram.ext")

# Make the classes instantiable in a way that returns predictable mocks.
_telegram_stub.InlineKeyboardButton = MagicMock(name="InlineKeyboardButton")
_telegram_stub.InlineKeyboardMarkup = MagicMock(name="InlineKeyboardMarkup")
_telegram_stub.Update = MagicMock(name="Update")

_telegram_ext_stub.Application = MagicMock(name="Application")
_telegram_ext_stub.CommandHandler = MagicMock(name="CommandHandler")
_telegram_ext_stub.ContextTypes = MagicMock(name="ContextTypes")
_telegram_ext_stub.CallbackQueryHandler = MagicMock(name="CallbackQueryHandler")

sys.modules.setdefault("telegram", _telegram_stub)
sys.modules.setdefault("telegram.ext", _telegram_ext_stub)

# ── 3. Stub out telethon packages ─────────────────────────────────────────────
_telethon_stub = MagicMock(name="telethon")
_telethon_sessions_stub = MagicMock(name="telethon.sessions")

_telethon_stub.TelegramClient = MagicMock(name="TelegramClient")
_telethon_sessions_stub.StringSession = MagicMock(name="StringSession")

sys.modules.setdefault("telethon", _telethon_stub)
sys.modules.setdefault("telethon.sessions", _telethon_sessions_stub)

# ── 4. Shared in-memory SQLite database ───────────────────────────────────────
# We create one in-memory connection and hand it back every time
# ``sqlite3.connect`` is called during module import.

_in_memory_conn = sqlite3.connect(":memory:", check_same_thread=False)

# ── 5. Import the bot module under the patches ────────────────────────────────
with patch("sqlite3.connect", return_value=_in_memory_conn):
    import ntn_mega_vouch_bot_polished as _bot_module  # noqa: E402

# Point the module's globals at our shared in-memory connection so that
# any direct manipulation of bot.cursor / bot.conn in tests works correctly.
_bot_module.conn = _in_memory_conn
_bot_module.cursor = _in_memory_conn.cursor()

# Re-create the schema inside the in-memory DB (the CREATE IF NOT EXISTS
# statements already ran during import, but we expose the cursor used by the
# module via the assignment above, so run them once more to be safe).
_bot_module.cursor.execute("""
    CREATE TABLE IF NOT EXISTS vouches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        giver_id INTEGER,
        giver_name TEXT,
        target TEXT,
        reason TEXT,
        type TEXT,
        status TEXT,
        created_at TEXT,
        feed_msg_id INTEGER
    )
""")
_bot_module.cursor.execute("""
    CREATE TABLE IF NOT EXISTS reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vouch_id INTEGER,
        user_id INTEGER,
        reaction TEXT
    )
""")
_bot_module.cursor.execute("""
    CREATE TABLE IF NOT EXISTS cooldowns (
        user_id INTEGER PRIMARY KEY,
        last_vouch_time INTEGER
    )
""")
_in_memory_conn.commit()
