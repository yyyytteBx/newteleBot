import os
import sys
import sqlite3
from unittest.mock import MagicMock, patch

# ── 1. Environment ────────────────────────────────────────────────────────────
os.environ.setdefault("BOT_TOKEN", "test_token_for_unit_tests")

# ── 2. Stub out the telegram packages ─────────────────────────────────────────
_telegram_stub = MagicMock(name="telegram")
_telegram_ext_stub = MagicMock(name="telegram.ext")

_telegram_stub.InlineKeyboardButton = MagicMock(name="InlineKeyboardButton")
_telegram_stub.InlineKeyboardMarkup = MagicMock(name="InlineKeyboardMarkup")
_telegram_stub.Update = MagicMock(name="Update")

_telegram_ext_stub.Application = MagicMock(name="Application")
_telegram_ext_stub.CommandHandler = MagicMock(name="CommandHandler")
_telegram_ext_stub.ContextTypes = MagicMock(name="ContextTypes")
_telegram_ext_stub.CallbackQueryHandler = MagicMock(name="CallbackQueryHandler")

sys.modules.setdefault("telegram", _telegram_stub)
sys.modules.setdefault("telegram.ext", _telegram_ext_stub)

# ── 2b. Stub out the telethon packages ────────────────────────────────────────
_telethon_stub = MagicMock(name="telethon")
_telethon_sessions_stub = MagicMock(name="telethon.sessions")
_telethon_tl_stub = MagicMock(name="telethon.tl")
_telethon_tl_functions_stub = MagicMock(name="telethon.tl.functions")
_telethon_tl_functions_contacts_stub = MagicMock(name="telethon.tl.functions.contacts")
_telethon_tl_types_stub = MagicMock(name="telethon.tl.types")

sys.modules.setdefault("telethon", _telethon_stub)
sys.modules.setdefault("telethon.sessions", _telethon_sessions_stub)
sys.modules.setdefault("telethon.tl", _telethon_tl_stub)
sys.modules.setdefault("telethon.tl.functions", _telethon_tl_functions_stub)
sys.modules.setdefault("telethon.tl.functions.contacts", _telethon_tl_functions_contacts_stub)
sys.modules.setdefault("telethon.tl.types", _telethon_tl_types_stub)

# ── 3. Shared in-memory SQLite database ───────────────────────────────────────
_in_memory_conn = sqlite3.connect(":memory:", check_same_thread=False)

# ── 4. Import the bot module under the patches ────────────────────────────────
with patch("sqlite3.connect", return_value=_in_memory_conn):
    import ntn_mega_vouch_bot_polished as _bot_module  # noqa: E402

_bot_module.conn = _in_memory_conn
_bot_module.cursor = _in_memory_conn.cursor()

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
