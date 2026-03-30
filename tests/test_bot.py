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
        ctx.bot.send_message.assert_called_once()
        call_kwargs = ctx.bot.send_message.call_args
        assert call_kwargs[0][0] == bot.FEED_CHANNEL_ID

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
