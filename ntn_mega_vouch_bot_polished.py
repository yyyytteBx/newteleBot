# NTN MEGA VOUCH BOT (POLISHED VERSION)
# Clean formatting, NTN titles, prettier outputs


import os
import sys
import sqlite3
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    sys.exit("ERROR: BOT_TOKEN environment variable is not set. Exiting.")

# Telethon userbot client (needed to resolve phone numbers / user IDs)
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

_telethon_client: TelegramClient | None = None

def get_telethon_client() -> TelegramClient | None:
    """Return a (possibly cached) Telethon client, or None if not configured."""
    global _telethon_client
    if not API_ID or not API_HASH or not SESSION_STRING:
        return None
    if _telethon_client is None:
        _telethon_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    return _telethon_client

FEED_CHANNEL_ID = -1003744224655
LOG_CHANNEL_ID = -1003305030576
ADMIN_IDS = [8299310648, 8672754119, 8543785070]
WHITELISTED_GROUPS = [-1003554554262, -1003776395663, -1003628456438]

MAX_VOUCHES_PER_DAY = 5
COOLDOWN_SECONDS = 60

conn = sqlite3.connect("vouches.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vouch_id INTEGER,
    user_id INTEGER,
    reaction TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_vouch_time INTEGER
)
""")

conn.commit()

# ---------- HELPERS ----------
def allowed(chat_id): return chat_id in WHITELISTED_GROUPS

def daily_vouch_count(user_id, vouch_type="vouch"):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) FROM vouches WHERE giver_id=? AND type=? AND created_at LIKE ?",
        (user_id, vouch_type, f"{today}%"),
    )
    return cursor.fetchone()[0]

def is_admin(uid): return uid in ADMIN_IDS

async def log(context, text):
    try:
        await context.bot.send_message(LOG_CHANNEL_ID, text)
    except: pass

def get_title(score):
    if score >= 100: return "🏆 Elite"
    elif score >= 50: return "💎 Trusted"
    elif score >= 20: return "🔹 Verified"
    elif score >= 5: return "🟢 Active"
    elif score >= 0: return "⚪ Member"
    else: return "🔻 Watchlist"

# ---------- BUTTONS ----------
def vote_buttons(vid, up=0, down=0):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"👍 {up}", callback_data=f"up_{vid}"),
        InlineKeyboardButton(f"👎 {down}", callback_data=f"down_{vid}")
    ]])

# ---------- VALIDATION ----------
def cooldown(user_id):
    now = int(time.time())
    cursor.execute("SELECT last_vouch_time FROM cooldowns WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row and now - row[0] < COOLDOWN_SECONDS:
        return COOLDOWN_SECONDS - (now - row[0])
    return 0

def set_cooldown(user_id):
    now = int(time.time())
    cursor.execute("INSERT OR REPLACE INTO cooldowns VALUES (?,?)", (user_id, now))
    conn.commit()

# ---------- COMMANDS ----------
async def vouch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    if len(context.args) < 2: return

    user = update.effective_user
    target = context.args[0]
    reason = " ".join(context.args[1:])
    username = user.username or str(user.id)

    if target.lower() == f"@{username}".lower():
        await update.message.reply_text("❌ No self vouching.")
        return

    if cooldown(user.id) > 0:
        await update.message.reply_text("⏳ Slow down.")
        return

    if daily_vouch_count(user.id) >= MAX_VOUCHES_PER_DAY:
        await update.message.reply_text(f"❌ Daily vouch limit ({MAX_VOUCHES_PER_DAY}) reached.")
        return

    set_cooldown(user.id)

    cursor.execute("INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
                   (update.effective_chat.id, user.id, username, target, reason, "vouch", "approved", datetime.now(timezone.utc).isoformat()))
    vid = cursor.lastrowid
    conn.commit()

    text = f"✨ VOUCH\n\n👤 {target}\n📝 {reason}\n\n— @{username}"

    try:
        msg = await context.bot.send_message(FEED_CHANNEL_ID, text, reply_markup=vote_buttons(vid))
        cursor.execute("UPDATE vouches SET feed_msg_id=? WHERE id=?", (msg.message_id, vid))
        conn.commit()
    except Exception:
        await update.message.reply_text("⚠️ Vouch saved but could not post to feed channel.")

    await log(context, f"✨ VOUCH | @{username} → {target} | {reason}")

# ---------- NEG ----------
async def neg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_chat.id): return
    if len(context.args) < 2: return

    user = update.effective_user
    target = context.args[0]
    reason = " ".join(context.args[1:])
    username = user.username or str(user.id)

    if target.lower() == f"@{username}".lower():
        await update.message.reply_text("❌ No self-reporting.")
        return

    if cooldown(user.id) > 0:
        await update.message.reply_text("⏳ Slow down.")
        return

    if daily_vouch_count(user.id, "neg") >= MAX_VOUCHES_PER_DAY:
        await update.message.reply_text(f"❌ Daily report limit ({MAX_VOUCHES_PER_DAY}) reached.")
        return

    set_cooldown(user.id)

    cursor.execute("INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
                   (update.effective_chat.id, user.id, username, target, reason, "neg", "approved", datetime.now(timezone.utc).isoformat()))
    vid = cursor.lastrowid
    conn.commit()

    text = f"⚠️ REPORT\n\n👤 {target}\n📝 {reason}\n\n— @{username}"

    try:
        msg = await context.bot.send_message(FEED_CHANNEL_ID, text, reply_markup=vote_buttons(vid))
        cursor.execute("UPDATE vouches SET feed_msg_id=? WHERE id=?", (msg.message_id, vid))
        conn.commit()
    except Exception:
        await update.message.reply_text("⚠️ Report saved but could not post to feed channel.")

    await log(context, f"⚠️ REPORT | @{username} → {target} | {reason}")


# ---------- REP ----------
async def rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.args[0] if context.args else (f"@{update.effective_user.username}" if update.effective_user.username else str(update.effective_user.id))

    cursor.execute("SELECT COUNT(*) FROM vouches WHERE target=? AND type='vouch' AND status='approved'", (target,))
    pos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vouches WHERE target=? AND type='neg' AND status='approved'", (target,))
    neg_count = cursor.fetchone()[0]

    score = pos - (neg_count * 2)
    title = get_title(score)

    text = f"📊 {target}\n\n⭐ {pos} | ⚠️ {neg_count}\n📈 Score: {score}\n🏷 {title}"
    await update.message.reply_text(text)

# ---------- LEADERBOARD ----------
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
    SELECT target, COUNT(*) as total
    FROM vouches
    WHERE type='vouch' AND status='approved'
    GROUP BY target
    ORDER BY total DESC
    LIMIT 10
    """)

    rows = cursor.fetchall()

    text = "🏆 NTN Leaderboard\n\n"
    for i, (user, total) in enumerate(rows, 1):
        text += f"{i}. {user} — {total} ⭐\n"

    await update.message.reply_text(text)

# ---------- CALLBACK ----------
async def buttons(update, context):
    q = update.callback_query
    await q.answer()
    vid = int(q.data.split("_")[1])

    cursor.execute("DELETE FROM reactions WHERE vouch_id=? AND user_id=?", (vid, q.from_user.id))
    cursor.execute("INSERT INTO reactions (vouch_id,user_id,reaction) VALUES (?,?,?)",
                   (vid, q.from_user.id, "up" if "up" in q.data else "down"))
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM reactions WHERE vouch_id=? AND reaction='up'", (vid,))
    up = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM reactions WHERE vouch_id=? AND reaction='down'", (vid,))
    down = cursor.fetchone()[0]

    await q.edit_message_reply_markup(vote_buttons(vid, up, down))

# ---------- LOOKUP (admin-only, Telethon) ----------
async def lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /lookup <phone|user_id>
    Resolves a phone number or numeric Telegram user ID to profile info.
    Admin-only.
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admins only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /lookup <phone_number or user_id>")
        return

    query = context.args[0].strip()

    client = get_telethon_client()
    if client is None:
        await update.message.reply_text("⚠️ Telethon is not configured (API_ID / API_HASH / SESSION_STRING missing).")
        return

    try:
        async with client:
            if query.lstrip("+").isdigit() and not query.startswith("+"):
                # Numeric ID lookup
                entity = await client.get_entity(int(query))
            else:
                # Phone number lookup — import as a temporary contact
                result = await client(ImportContactsRequest([
                    InputPhoneContact(client_id=0, phone=query, first_name="Lookup", last_name="")
                ]))
                if not result.users:
                    await update.message.reply_text("❌ No Telegram account found for that phone number.")
                    return
                entity = result.users[0]

        uid = entity.id
        first = getattr(entity, "first_name", "") or ""
        last = getattr(entity, "last_name", "") or ""
        username = getattr(entity, "username", None)
        name = f"{first} {last}".strip() or "—"
        uname_str = f"@{username}" if username else "—"

        await update.message.reply_text(
            f"🔍 Lookup Result\n\n"
            f"👤 Name: {name}\n"
            f"🆔 Account ID: {uid}\n"
            f"📛 Username: {uname_str}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lookup failed: {e}")


# ---------- MAIN ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("vouch", vouch))
    app.add_handler(CommandHandler("neg", neg))
    app.add_handler(CommandHandler("rep", rep))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("lookup", lookup))
    app.add_handler(CallbackQueryHandler(buttons))

    print("NTN POLISHED BOT RUNNING")
    app.run_polling()

if __name__ == "__main__":
    main()
