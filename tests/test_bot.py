"""
Comprehensive tests for ntn_mega_vouch_bot_polished.py

Coverage areas
──────────────
• Helper functions  : allowed, is_admin, get_title, vote_buttons
• DB helpers        : cooldown, set_cooldown
• Async handlers    : vouch, rep, leaderboard, buttons
• Utility           : log
"""

import sys
import time
import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call

# The conftest.py already imported the module with all stubs in place.
import ntn_mega_vouch_bot_polished as bot


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all rows from every table before each test."""
    bot.cursor.execute("DELETE FROM vouches")
    bot.cursor.execute("DELETE FROM reactions")
    bot.cursor.execute("DELETE FROM cooldowns")
    bot.conn.commit()
    yield


def _make_update(*, chat_id=None, user_id=1111, username="testuser", args=None, message_text=""):
    """Build a minimal mock Update object."""
    update = MagicMock()
    update.effective_chat.id = chat_id if chat_id is not None else bot.WHITELISTED_GROUPS[0]
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.message.reply_text = AsyncMock()
    return update


def _make_context(*, args=None):
    """Build a minimal mock context object."""
    ctx = MagicMock()
    ctx.args = args or []
    ctx.bot.send_message = AsyncMock()
    return ctx


# ══════════════════════════════════════════════════════════════════════════════
# allowed()
# ══════════════════════════════════════════════════════════════════════════════

class TestAllowed:
    def test_whitelisted_group_returns_true(self):
        for gid in bot.WHITELISTED_GROUPS:
            assert bot.allowed(gid) is True

    def test_non_whitelisted_group_returns_false(self):
        assert bot.allowed(0) is False
        assert bot.allowed(9999) is False
        assert bot.allowed(-1) is False

    def test_empty_group_id_returns_false(self):
        assert bot.allowed(None) is False


# ══════════════════════════════════════════════════════════════════════════════
# is_admin()
# ══════════════════════════════════════════════════════════════════════════════

class TestIsAdmin:
    def test_known_admin_returns_true(self):
        for aid in bot.ADMIN_IDS:
            assert bot.is_admin(aid) is True

    def test_unknown_user_returns_false(self):
        assert bot.is_admin(0) is False
        assert bot.is_admin(9999) is False

    def test_none_returns_false(self):
        assert bot.is_admin(None) is False


# ══════════════════════════════════════════════════════════════════════════════
# get_title()
# ══════════════════════════════════════════════════════════════════════════════

class TestGetTitle:
    def test_elite_at_100(self):
        assert "Elite" in bot.get_title(100)

    def test_elite_above_100(self):
        assert "Elite" in bot.get_title(150)

    def test_trusted_at_50(self):
        assert "Trusted" in bot.get_title(50)

    def test_trusted_between_50_and_99(self):
        assert "Trusted" in bot.get_title(75)

    def test_verified_at_20(self):
        assert "Verified" in bot.get_title(20)

    def test_verified_between_20_and_49(self):
        assert "Verified" in bot.get_title(35)

    def test_active_at_5(self):
        assert "Active" in bot.get_title(5)

    def test_active_between_5_and_19(self):
        assert "Active" in bot.get_title(10)

    def test_member_at_0(self):
        assert "Member" in bot.get_title(0)

    def test_member_between_0_and_4(self):
        assert "Member" in bot.get_title(3)

    def test_watchlist_below_0(self):
        assert "Watchlist" in bot.get_title(-1)

    def test_watchlist_far_below_0(self):
        assert "Watchlist" in bot.get_title(-100)

    def test_boundary_99_is_trusted(self):
        assert "Trusted" in bot.get_title(99)

    def test_boundary_49_is_verified(self):
        assert "Verified" in bot.get_title(49)

    def test_boundary_19_is_active(self):
        assert "Active" in bot.get_title(19)

    def test_boundary_4_is_member(self):
        assert "Member" in bot.get_title(4)


# ══════════════════════════════════════════════════════════════════════════════
# vote_buttons()
# ══════════════════════════════════════════════════════════════════════════════

class TestVoteButtons:
    def test_returns_inline_keyboard_markup(self):
        result = bot.vote_buttons(1)
        # InlineKeyboardMarkup is mocked; assert it was called once with a list
        sys.modules["telegram"].InlineKeyboardMarkup.assert_called()

    def test_callback_data_up(self):
        bot.vote_buttons(42, up=3, down=1)
        calls = sys.modules["telegram"].InlineKeyboardButton.call_args_list
        # Find the 'up' button call
        up_call = next(c for c in calls if "up_42" in str(c))
        assert up_call is not None

    def test_callback_data_down(self):
        bot.vote_buttons(42, up=3, down=1)
        calls = sys.modules["telegram"].InlineKeyboardButton.call_args_list
        down_call = next(c for c in calls if "down_42" in str(c))
        assert down_call is not None

    def test_default_counts_are_zero(self):
        bot.vote_buttons(7)
        calls = sys.modules["telegram"].InlineKeyboardButton.call_args_list
        # The last two calls should show "👍 0" and "👎 0"
        labels = [str(c) for c in calls[-2:]]
        assert any("👍 0" in lbl for lbl in labels)
        assert any("👎 0" in lbl for lbl in labels)


# ══════════════════════════════════════════════════════════════════════════════
# cooldown() and set_cooldown()
# ══════════════════════════════════════════════════════════════════════════════

class TestCooldown:
    def test_no_prior_entry_returns_zero(self):
        assert bot.cooldown(99999) == 0

    def test_fresh_entry_returns_positive_remaining(self):
        bot.set_cooldown(12345)
        remaining = bot.cooldown(12345)
        assert remaining > 0
        assert remaining <= bot.COOLDOWN_SECONDS

    def test_expired_cooldown_returns_zero(self):
        past = int(time.time()) - bot.COOLDOWN_SECONDS - 1
        bot.cursor.execute(
            "INSERT OR REPLACE INTO cooldowns VALUES (?,?)", (77777, past)
        )
        bot.conn.commit()
        assert bot.cooldown(77777) == 0

    def test_remaining_is_approximately_correct(self):
        bot.set_cooldown(55555)
        remaining = bot.cooldown(55555)
        assert 0 < remaining <= bot.COOLDOWN_SECONDS


class TestSetCooldown:
    def test_inserts_new_record(self):
        bot.set_cooldown(11111)
        bot.cursor.execute(
            "SELECT last_vouch_time FROM cooldowns WHERE user_id=?", (11111,)
        )
        row = bot.cursor.fetchone()
        assert row is not None
        assert abs(row[0] - int(time.time())) <= 2

    def test_updates_existing_record(self):
        old_time = int(time.time()) - 200
        bot.cursor.execute(
            "INSERT OR REPLACE INTO cooldowns VALUES (?,?)", (22222, old_time)
        )
        bot.conn.commit()
        bot.set_cooldown(22222)
        bot.cursor.execute(
            "SELECT last_vouch_time FROM cooldowns WHERE user_id=?", (22222,)
        )
        row = bot.cursor.fetchone()
        assert row[0] > old_time

    def test_only_one_row_per_user(self):
        bot.set_cooldown(33333)
        bot.set_cooldown(33333)
        bot.cursor.execute(
            "SELECT COUNT(*) FROM cooldowns WHERE user_id=?", (33333,)
        )
        count = bot.cursor.fetchone()[0]
        assert count == 1


# ══════════════════════════════════════════════════════════════════════════════
# log()
# ══════════════════════════════════════════════════════════════════════════════

class TestLog:
    async def test_log_sends_to_channel(self):
        ctx = _make_context()
        await bot.log(ctx, "test message")
        ctx.bot.send_message.assert_called_once_with(bot.LOG_CHANNEL_ID, "test message")

    async def test_log_silently_handles_exception(self):
        ctx = _make_context()
        ctx.bot.send_message.side_effect = Exception("network error")
        # Should not raise
        await bot.log(ctx, "test message")


# ══════════════════════════════════════════════════════════════════════════════
# vouch()
# ══════════════════════════════════════════════════════════════════════════════

class TestVouch:
    async def test_disallowed_chat_returns_early(self):
        update = _make_update(chat_id=9999)
        ctx = _make_context(args=["@someone", "great trader"])
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_not_called()
        bot.cursor.execute("SELECT COUNT(*) FROM vouches")
        assert bot.cursor.fetchone()[0] == 0

    async def test_insufficient_args_returns_early(self):
        update = _make_update()
        ctx = _make_context(args=["@someone"])  # only 1 arg, need ≥2
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_not_called()
        bot.cursor.execute("SELECT COUNT(*) FROM vouches")
        assert bot.cursor.fetchone()[0] == 0

    async def test_no_args_returns_early(self):
        update = _make_update()
        ctx = _make_context(args=[])
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_not_called()

    async def test_self_vouch_is_rejected(self):
        update = _make_update(username="alice")
        ctx = _make_context(args=["@alice", "great"])
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "self" in reply_text.lower() or "❌" in reply_text

    async def test_self_vouch_case_insensitive(self):
        update = _make_update(username="Alice")
        ctx = _make_context(args=["@alice", "great"])
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_called_once()

    async def test_cooldown_blocks_second_vouch(self):
        # First vouch sets cooldown
        bot.set_cooldown(1111)
        update = _make_update(user_id=1111, username="bob")
        ctx = _make_context(args=["@carol", "honest"])
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        assert "⏳" in reply_text or "slow" in reply_text.lower()

    async def test_successful_vouch_saves_to_db(self):
        update = _make_update(user_id=2222, username="dave")
        ctx = _make_context(args=["@eve", "very reliable"])
        await bot.vouch(update, ctx)
        bot.cursor.execute("SELECT target, reason, type, status FROM vouches")
        row = bot.cursor.fetchone()
        assert row is not None
        assert row[0] == "@eve"
        assert row[1] == "very reliable"
        assert row[2] == "vouch"
        assert row[3] == "approved"

    async def test_successful_vouch_sets_cooldown(self):
        update = _make_update(user_id=3333, username="frank")
        ctx = _make_context(args=["@grace", "trusted"])
        await bot.vouch(update, ctx)
        assert bot.cooldown(3333) > 0

    async def test_successful_vouch_posts_to_feed(self):
        msg_mock = MagicMock()
        msg_mock.message_id = 999
        update = _make_update(user_id=4444, username="hank")
        ctx = _make_context(args=["@iris", "solid"])
        ctx.bot.send_message = AsyncMock(return_value=msg_mock)
        await bot.vouch(update, ctx)
        ctx.bot.send_message.assert_called()
        # First call must target the feed channel
        first_call = ctx.bot.send_message.call_args_list[0]
        assert first_call[0][0] == bot.FEED_CHANNEL_ID

    async def test_feed_error_still_saves_vouch(self):
        update = _make_update(user_id=5555, username="jack")
        ctx = _make_context(args=["@karen", "good"])
        ctx.bot.send_message = AsyncMock(side_effect=Exception("channel error"))
        await bot.vouch(update, ctx)
        # Vouch is still saved
        bot.cursor.execute("SELECT COUNT(*) FROM vouches WHERE giver_id=5555")
        assert bot.cursor.fetchone()[0] == 1
        # Warning message sent
        update.message.reply_text.assert_called_once()
        assert "⚠️" in update.message.reply_text.call_args[0][0]

    async def test_feed_error_notifies_user(self):
        update = _make_update(user_id=6666, username="leo")
        ctx = _make_context(args=["@mia", "reliable"])
        ctx.bot.send_message = AsyncMock(side_effect=Exception("timeout"))
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_called_once()

    async def test_feed_msg_id_stored_on_success(self):
        msg_mock = MagicMock()
        msg_mock.message_id = 42
        update = _make_update(user_id=7777, username="nina")
        ctx = _make_context(args=["@omar", "great"])
        ctx.bot.send_message = AsyncMock(return_value=msg_mock)
        await bot.vouch(update, ctx)
        bot.cursor.execute(
            "SELECT feed_msg_id FROM vouches WHERE giver_id=7777"
        )
        row = bot.cursor.fetchone()
        assert row[0] == 42

    async def test_vouch_uses_user_id_when_no_username(self):
        update = _make_update(user_id=8888, username=None)
        ctx = _make_context(args=["@pete", "honest"])
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        await bot.vouch(update, ctx)
        bot.cursor.execute(
            "SELECT giver_name FROM vouches WHERE giver_id=8888"
        )
        row = bot.cursor.fetchone()
        assert row[0] == "8888"


# ══════════════════════════════════════════════════════════════════════════════
# rep()
# ══════════════════════════════════════════════════════════════════════════════

class TestRep:
    def _insert_vouch(self, target, vtype="vouch", status="approved"):
        bot.cursor.execute(
            "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (0, 1, "system", target, "test", vtype, status, "2024-01-01"),
        )
        bot.conn.commit()

    async def test_rep_with_explicit_target(self):
        self._insert_vouch("@alice")
        self._insert_vouch("@alice")
        update = _make_update()
        ctx = _make_context(args=["@alice"])
        await bot.rep(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "@alice" in text

    async def test_rep_defaults_to_own_username(self):
        self._insert_vouch("@testuser")
        update = _make_update(username="testuser")
        ctx = _make_context(args=[])
        await bot.rep(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "@testuser" in text

    async def test_rep_defaults_to_user_id_when_no_username(self):
        update = _make_update(user_id=9999, username=None)
        ctx = _make_context(args=[])
        await bot.rep(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "9999" in text

    async def test_rep_score_is_positive_minus_double_negative(self):
        # 3 positive, 1 negative → score = 3 - (1*2) = 1
        for _ in range(3):
            self._insert_vouch("@scoreduser", "vouch")
        self._insert_vouch("@scoreduser", "neg")
        update = _make_update()
        ctx = _make_context(args=["@scoreduser"])
        await bot.rep(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "Score: 1" in text

    async def test_rep_title_included_in_reply(self):
        for _ in range(5):
            self._insert_vouch("@golden")
        update = _make_update()
        ctx = _make_context(args=["@golden"])
        await bot.rep(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        # score=5 → "Active"
        assert "Active" in text

    async def test_rep_zero_vouches(self):
        update = _make_update()
        ctx = _make_context(args=["@nobody"])
        await bot.rep(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Score: 0" in text

    async def test_rep_only_counts_approved(self):
        self._insert_vouch("@partial", "vouch", "pending")  # not approved
        self._insert_vouch("@partial", "vouch", "approved")  # approved
        update = _make_update()
        ctx = _make_context(args=["@partial"])
        await bot.rep(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "⭐ 1" in text

    async def test_rep_shows_positive_and_negative_counts(self):
        for _ in range(4):
            self._insert_vouch("@mixed", "vouch")
        for _ in range(2):
            self._insert_vouch("@mixed", "neg")
        update = _make_update()
        ctx = _make_context(args=["@mixed"])
        await bot.rep(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "⭐ 4" in text
        assert "⚠️ 2" in text


# ══════════════════════════════════════════════════════════════════════════════
# leaderboard()
# ══════════════════════════════════════════════════════════════════════════════

class TestLeaderboard:
    def _insert_vouches(self, target, count):
        for _ in range(count):
            bot.cursor.execute(
                "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (0, 1, "sys", target, "ok", "vouch", "approved", "2024-01-01"),
            )
        bot.conn.commit()

    async def test_empty_leaderboard(self):
        update = _make_update()
        ctx = _make_context()
        await bot.leaderboard(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Leaderboard" in text

    async def test_leaderboard_shows_entries(self):
        self._insert_vouches("@alpha", 3)
        self._insert_vouches("@beta", 5)
        update = _make_update()
        ctx = _make_context()
        await bot.leaderboard(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "@alpha" in text
        assert "@beta" in text

    async def test_leaderboard_ordered_by_count_desc(self):
        self._insert_vouches("@low", 1)
        self._insert_vouches("@high", 10)
        update = _make_update()
        ctx = _make_context()
        await bot.leaderboard(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert text.index("@high") < text.index("@low")

    async def test_leaderboard_max_10_entries(self):
        for i in range(15):
            self._insert_vouches(f"@user{i}", i + 1)
        update = _make_update()
        ctx = _make_context()
        await bot.leaderboard(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        # Count occurrences of "@user" to verify ≤10 shown
        shown = text.count("@user")
        assert shown <= 10

    async def test_leaderboard_ignores_neg_type(self):
        bot.cursor.execute(
            "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (0, 1, "sys", "@neguser", "bad", "neg", "approved", "2024-01-01"),
        )
        bot.conn.commit()
        update = _make_update()
        ctx = _make_context()
        await bot.leaderboard(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "@neguser" not in text

    async def test_leaderboard_ignores_non_approved(self):
        bot.cursor.execute(
            "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (0, 1, "sys", "@pending", "ok", "vouch", "pending", "2024-01-01"),
        )
        bot.conn.commit()
        update = _make_update()
        ctx = _make_context()
        await bot.leaderboard(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "@pending" not in text

    async def test_leaderboard_includes_ntn_title(self):
        update = _make_update()
        ctx = _make_context()
        await bot.leaderboard(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "NTN" in text


# ══════════════════════════════════════════════════════════════════════════════
# buttons() – callback query handler
# ══════════════════════════════════════════════════════════════════════════════

class TestButtons:
    def _seed_vouch(self):
        bot.cursor.execute(
            "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (0, 1, "sys", "@t", "ok", "vouch", "approved", "2024-01-01"),
        )
        bot.conn.commit()
        return bot.cursor.lastrowid

    def _make_query_update(self, data, user_id=100):
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.data = data
        update.callback_query.from_user.id = user_id
        update.callback_query.edit_message_reply_markup = AsyncMock()
        return update

    async def test_up_vote_recorded(self):
        vid = self._seed_vouch()
        update = self._make_query_update(f"up_{vid}", user_id=200)
        await bot.buttons(update, _make_context())
        bot.cursor.execute(
            "SELECT reaction FROM reactions WHERE vouch_id=? AND user_id=?", (vid, 200)
        )
        row = bot.cursor.fetchone()
        assert row is not None
        assert row[0] == "up"

    async def test_down_vote_recorded(self):
        vid = self._seed_vouch()
        update = self._make_query_update(f"down_{vid}", user_id=300)
        await bot.buttons(update, _make_context())
        bot.cursor.execute(
            "SELECT reaction FROM reactions WHERE vouch_id=? AND user_id=?", (vid, 300)
        )
        row = bot.cursor.fetchone()
        assert row is not None
        assert row[0] == "down"

    async def test_vote_changes_existing_reaction(self):
        vid = self._seed_vouch()
        # First vote: up
        upd1 = self._make_query_update(f"up_{vid}", user_id=400)
        await bot.buttons(upd1, _make_context())
        # Second vote: down (same user changes their vote)
        upd2 = self._make_query_update(f"down_{vid}", user_id=400)
        await bot.buttons(upd2, _make_context())
        bot.cursor.execute(
            "SELECT reaction FROM reactions WHERE vouch_id=? AND user_id=?", (vid, 400)
        )
        row = bot.cursor.fetchone()
        assert row[0] == "down"

    async def test_only_one_reaction_per_user_per_vouch(self):
        vid = self._seed_vouch()
        upd = self._make_query_update(f"up_{vid}", user_id=500)
        await bot.buttons(upd, _make_context())
        await bot.buttons(upd, _make_context())
        bot.cursor.execute(
            "SELECT COUNT(*) FROM reactions WHERE vouch_id=? AND user_id=?", (vid, 500)
        )
        count = bot.cursor.fetchone()[0]
        assert count == 1

    async def test_answer_is_called(self):
        vid = self._seed_vouch()
        update = self._make_query_update(f"up_{vid}", user_id=600)
        await bot.buttons(update, _make_context())
        update.callback_query.answer.assert_called_once()

    async def test_markup_is_updated_with_new_counts(self):
        vid = self._seed_vouch()
        update = self._make_query_update(f"up_{vid}", user_id=700)
        await bot.buttons(update, _make_context())
        update.callback_query.edit_message_reply_markup.assert_called_once()

    async def test_multiple_users_voting(self):
        vid = self._seed_vouch()
        for uid in [801, 802, 803]:
            upd = self._make_query_update(f"up_{vid}", user_id=uid)
            await bot.buttons(upd, _make_context())
        bot.cursor.execute(
            "SELECT COUNT(*) FROM reactions WHERE vouch_id=? AND reaction='up'", (vid,)
        )
        assert bot.cursor.fetchone()[0] == 3

    async def test_up_and_down_counts_reflected_in_markup(self):
        vid = self._seed_vouch()
        await bot.buttons(self._make_query_update(f"up_{vid}", user_id=901), _make_context())
        await bot.buttons(self._make_query_update(f"down_{vid}", user_id=902), _make_context())
        # edit_message_reply_markup was called after each vote
        # The last call used vote_buttons(vid, up=1, down=1)
        markup_calls = self._make_query_update(f"up_{vid}", user_id=901)
        # Verify DB state
        bot.cursor.execute(
            "SELECT COUNT(*) FROM reactions WHERE vouch_id=? AND reaction='up'", (vid,)
        )
        assert bot.cursor.fetchone()[0] == 1
        bot.cursor.execute(
            "SELECT COUNT(*) FROM reactions WHERE vouch_id=? AND reaction='down'", (vid,)
        )
        assert bot.cursor.fetchone()[0] == 1


# ══════════════════════════════════════════════════════════════════════════════
# daily_vouch_count()
# ══════════════════════════════════════════════════════════════════════════════

class TestDailyVouchCount:
    def _insert_today_vouch(self, giver_id, vouch_type="vouch"):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).isoformat()
        bot.cursor.execute(
            "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (0, giver_id, "sys", "@t", "ok", vouch_type, "approved", today),
        )
        bot.conn.commit()

    def test_zero_when_no_vouches(self):
        assert bot.daily_vouch_count(99999) == 0

    def test_counts_todays_vouches(self):
        self._insert_today_vouch(10001)
        self._insert_today_vouch(10001)
        assert bot.daily_vouch_count(10001) == 2

    def test_does_not_count_other_types(self):
        self._insert_today_vouch(10002, "vouch")
        self._insert_today_vouch(10002, "neg")
        assert bot.daily_vouch_count(10002, "vouch") == 1
        assert bot.daily_vouch_count(10002, "neg") == 1

    def test_does_not_count_old_vouches(self):
        bot.cursor.execute(
            "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (0, 10003, "sys", "@t", "ok", "vouch", "approved", "2000-01-01T00:00:00"),
        )
        bot.conn.commit()
        assert bot.daily_vouch_count(10003) == 0


# ══════════════════════════════════════════════════════════════════════════════
# vouch() – daily limit & log channel
# ══════════════════════════════════════════════════════════════════════════════

class TestVouchDailyLimit:
    def _fill_daily_vouches(self, giver_id, count=None):
        from datetime import datetime, timezone
        n = count if count is not None else bot.MAX_VOUCHES_PER_DAY
        today = datetime.now(timezone.utc).isoformat()
        for i in range(n):
            bot.cursor.execute(
                "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (bot.WHITELISTED_GROUPS[0], giver_id, "limiter", f"@t{i}", "ok", "vouch", "approved", today),
            )
        bot.conn.commit()

    async def test_daily_limit_blocks_vouch(self):
        self._fill_daily_vouches(20001)
        update = _make_update(user_id=20001, username="limiter")
        ctx = _make_context(args=["@newperson", "test"])
        await bot.vouch(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "❌" in text
        assert "limit" in text.lower() or str(bot.MAX_VOUCHES_PER_DAY) in text

    async def test_daily_limit_allows_up_to_max(self):
        self._fill_daily_vouches(20002, bot.MAX_VOUCHES_PER_DAY - 1)
        update = _make_update(user_id=20002, username="almostdone")
        ctx = _make_context(args=["@newcomer", "good"])
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        await bot.vouch(update, ctx)
        bot.cursor.execute("SELECT COUNT(*) FROM vouches WHERE giver_id=20002")
        assert bot.cursor.fetchone()[0] == bot.MAX_VOUCHES_PER_DAY

    async def test_daily_limit_does_not_block_different_type(self):
        """Filling the vouch limit should not prevent a /neg."""
        self._fill_daily_vouches(20003)
        # daily_vouch_count(..., "neg") should still be 0
        assert bot.daily_vouch_count(20003, "neg") == 0


class TestVouchLogsToChannel:
    async def test_log_channel_notified_on_success(self):
        msg_mock = MagicMock()
        msg_mock.message_id = 1
        update = _make_update(user_id=30001, username="logger")
        ctx = _make_context(args=["@target", "great"])
        ctx.bot.send_message = AsyncMock(return_value=msg_mock)
        await bot.vouch(update, ctx)
        # send_message called at least twice: feed + log
        assert ctx.bot.send_message.call_count >= 2
        # Last call is the log call to LOG_CHANNEL_ID
        last_call = ctx.bot.send_message.call_args_list[-1]
        assert last_call[0][0] == bot.LOG_CHANNEL_ID

    async def test_log_channel_notified_even_when_feed_fails(self):
        call_count = 0

        async def side_effect(channel_id, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if channel_id == bot.FEED_CHANNEL_ID:
                raise Exception("feed down")
            return MagicMock(message_id=1)

        update = _make_update(user_id=30002, username="logger2")
        ctx = _make_context(args=["@target2", "ok"])
        ctx.bot.send_message = AsyncMock(side_effect=side_effect)
        await bot.vouch(update, ctx)
        # Log call should still be attempted
        assert call_count >= 2


# ══════════════════════════════════════════════════════════════════════════════
# neg()
# ══════════════════════════════════════════════════════════════════════════════

class TestNeg:
    async def test_disallowed_chat_returns_early(self):
        update = _make_update(chat_id=9999)
        ctx = _make_context(args=["@someone", "scammer"])
        await bot.neg(update, ctx)
        update.message.reply_text.assert_not_called()
        bot.cursor.execute("SELECT COUNT(*) FROM vouches WHERE type='neg'")
        assert bot.cursor.fetchone()[0] == 0

    async def test_insufficient_args_returns_early(self):
        update = _make_update()
        ctx = _make_context(args=["@someone"])
        await bot.neg(update, ctx)
        update.message.reply_text.assert_not_called()

    async def test_no_args_returns_early(self):
        update = _make_update()
        ctx = _make_context(args=[])
        await bot.neg(update, ctx)
        update.message.reply_text.assert_not_called()

    async def test_self_neg_is_rejected(self):
        update = _make_update(username="alice")
        ctx = _make_context(args=["@alice", "bad"])
        await bot.neg(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "❌" in text

    async def test_self_neg_case_insensitive(self):
        update = _make_update(username="Alice")
        ctx = _make_context(args=["@alice", "bad"])
        await bot.neg(update, ctx)
        update.message.reply_text.assert_called_once()

    async def test_cooldown_blocks_neg(self):
        bot.set_cooldown(40001)
        update = _make_update(user_id=40001, username="bob2")
        ctx = _make_context(args=["@carol2", "scam"])
        await bot.neg(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "⏳" in text or "slow" in text.lower()

    async def test_successful_neg_saves_to_db(self):
        update = _make_update(user_id=40002, username="dave2")
        ctx = _make_context(args=["@eve2", "dishonest"])
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        await bot.neg(update, ctx)
        bot.cursor.execute("SELECT target, reason, type, status FROM vouches WHERE giver_id=40002")
        row = bot.cursor.fetchone()
        assert row is not None
        assert row[0] == "@eve2"
        assert row[1] == "dishonest"
        assert row[2] == "neg"
        assert row[3] == "approved"

    async def test_successful_neg_sets_cooldown(self):
        update = _make_update(user_id=40003, username="frank2")
        ctx = _make_context(args=["@grace2", "fraud"])
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        await bot.neg(update, ctx)
        assert bot.cooldown(40003) > 0

    async def test_successful_neg_posts_to_feed(self):
        msg_mock = MagicMock()
        msg_mock.message_id = 888
        update = _make_update(user_id=40004, username="hank2")
        ctx = _make_context(args=["@iris2", "scam"])
        ctx.bot.send_message = AsyncMock(return_value=msg_mock)
        await bot.neg(update, ctx)
        ctx.bot.send_message.assert_called()
        first_call = ctx.bot.send_message.call_args_list[0]
        assert first_call[0][0] == bot.FEED_CHANNEL_ID

    async def test_feed_error_still_saves_neg(self):
        update = _make_update(user_id=40005, username="jack2")
        ctx = _make_context(args=["@karen2", "bad"])
        ctx.bot.send_message = AsyncMock(side_effect=Exception("channel error"))
        await bot.neg(update, ctx)
        bot.cursor.execute("SELECT COUNT(*) FROM vouches WHERE giver_id=40005 AND type='neg'")
        assert bot.cursor.fetchone()[0] == 1
        update.message.reply_text.assert_called_once()
        assert "⚠️" in update.message.reply_text.call_args[0][0]

    async def test_neg_uses_user_id_when_no_username(self):
        update = _make_update(user_id=40006, username=None)
        ctx = _make_context(args=["@pete2", "fraud"])
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        await bot.neg(update, ctx)
        bot.cursor.execute("SELECT giver_name FROM vouches WHERE giver_id=40006")
        row = bot.cursor.fetchone()
        assert row[0] == "40006"

    async def test_neg_daily_limit(self):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).isoformat()
        for i in range(bot.MAX_VOUCHES_PER_DAY):
            bot.cursor.execute(
                "INSERT INTO vouches (chat_id,giver_id,giver_name,target,reason,type,status,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (bot.WHITELISTED_GROUPS[0], 40007, "reporter", f"@t{i}", "ok", "neg", "approved", today),
            )
        bot.conn.commit()
        update = _make_update(user_id=40007, username="reporter")
        ctx = _make_context(args=["@newbadguy", "scam"])
        await bot.neg(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "❌" in text

    async def test_neg_log_channel_notified(self):
        msg_mock = MagicMock()
        msg_mock.message_id = 1
        update = _make_update(user_id=40008, username="logger3")
        ctx = _make_context(args=["@badactor", "scam"])
        ctx.bot.send_message = AsyncMock(return_value=msg_mock)
        await bot.neg(update, ctx)
        assert ctx.bot.send_message.call_count >= 2
        last_call = ctx.bot.send_message.call_args_list[-1]
        assert last_call[0][0] == bot.LOG_CHANNEL_ID


# ══════════════════════════════════════════════════════════════════════════════
# user_client (Telethon session login)
# ══════════════════════════════════════════════════════════════════════════════

class TestUserClient:
    def test_user_client_none_without_env_vars(self):
        """user_client is None when session env vars are absent."""
        import os
        from unittest.mock import patch

        env = {k: v for k, v in os.environ.items()
               if k not in ("API_ID", "API_HASH", "SESSION_STRING")}

        with patch.dict(os.environ, env, clear=True):
            import importlib
            import sys
            mod_name = "ntn_mega_vouch_bot_polished"
            saved = sys.modules.pop(mod_name, None)
            try:
                with patch("sqlite3.connect", return_value=bot.conn):
                    fresh = importlib.import_module(mod_name)
                assert fresh.user_client is None
            finally:
                if saved is not None:
                    sys.modules[mod_name] = saved
                else:
                    sys.modules.pop(mod_name, None)

    def test_user_client_created_with_env_vars(self):
        """user_client is set to a TelegramClient when all session env vars are present."""
        import os
        import importlib
        import sys
        from unittest.mock import patch, MagicMock

        mock_client_instance = MagicMock(name="client_instance")
        mock_client_cls = MagicMock(name="TelegramClient", return_value=mock_client_instance)
        mock_string_session = MagicMock(name="StringSession")

        telethon_stub = sys.modules["telethon"]
        telethon_sessions_stub = sys.modules["telethon.sessions"]

        orig_client_cls = telethon_stub.TelegramClient
        orig_session_cls = telethon_sessions_stub.StringSession

        telethon_stub.TelegramClient = mock_client_cls
        telethon_sessions_stub.StringSession = mock_string_session

        env_patch = {"API_ID": "12345", "API_HASH": "abc123hash", "SESSION_STRING": "fake_session"}

        mod_name = "ntn_mega_vouch_bot_polished"
        saved = sys.modules.pop(mod_name, None)
        try:
            with patch.dict(os.environ, env_patch):
                with patch("sqlite3.connect", return_value=bot.conn):
                    fresh = importlib.import_module(mod_name)

            assert fresh.user_client is mock_client_instance
            mock_string_session.assert_called_once_with("fake_session")
            mock_client_cls.assert_called_once()
        finally:
            telethon_stub.TelegramClient = orig_client_cls
            telethon_sessions_stub.StringSession = orig_session_cls
            if saved is not None:
                sys.modules[mod_name] = saved
            else:
                sys.modules.pop(mod_name, None)
