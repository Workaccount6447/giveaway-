"""
handlers/stats.py

/stats          — superadmin: bot-wide statistics
/getgiveaway    — superadmin: retrieve archived giveaway JSON from DATABASE_CHANNEL
/oldgiveaway    — superadmin OR giveaway creator: list old giveaways + fetch by ID
/deleteold      — superadmin: delete archive metadata older than N months
/db             — superadmin: show database storage info (Total / Left in MB)
/broadcast      — superadmin: broadcast a message to all main-bot users
"""
from __future__ import annotations

import asyncio
import logging
import os
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram import F

from config.settings import settings

router = Router()
logger = logging.getLogger(__name__)


class BroadcastForm(StatesGroup):
    waiting_message = State()


def _is_superadmin(user_id: int) -> bool:
    return user_id in settings.SUPERADMIN_IDS


# ─── /stats ──────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not _is_superadmin(message.from_user.id):
        await message.answer("🚫 This command is for superadmins only.")
        return

    from utils.db import get_db, is_mongo, get_sqlite_path

    try:
        if is_mongo():
            db = get_db()
            total_users      = await db.main_bot_users.count_documents({})
            total_giveaways  = await db.giveaways.count_documents({})
            live_giveaways   = await db.giveaways.count_documents({"is_active": True})
            closed_giveaways = await db.giveaways.count_documents({"is_active": False})
            archived         = await db.giveaway_archive_refs.count_documents({})
            total_votes = 0
            async for g in db.giveaways.find({}, {"total_votes": 1}):
                total_votes += g.get("total_votes", 0)
            total_clones = await db.clone_bots.count_documents({"is_active": True})
            banned_users = await db.main_bot_users.count_documents({"is_banned": True})
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                async def cnt(q, p=()):
                    async with conn.execute(q, p) as c:
                        return (await c.fetchone())[0]
                total_users      = await cnt("SELECT COUNT(*) FROM main_bot_users")
                total_giveaways  = await cnt("SELECT COUNT(*) FROM giveaways")
                live_giveaways   = await cnt("SELECT COUNT(*) FROM giveaways WHERE is_active=1")
                closed_giveaways = await cnt("SELECT COUNT(*) FROM giveaways WHERE is_active=0")
                try:
                    archived = await cnt("SELECT COUNT(*) FROM giveaway_archive_refs")
                except Exception:
                    archived = 0
                total_votes  = await cnt("SELECT COALESCE(SUM(total_votes),0) FROM giveaways")
                total_clones = await cnt("SELECT COUNT(*) FROM clone_bots WHERE is_active=1")
                banned_users = await cnt("SELECT COUNT(*) FROM main_bot_users WHERE is_banned=1")

        await message.answer(
            "📊 <b>Bot Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>Total Users :</b> <code>{total_users:,}</code>\n"
            f"🎁 <b>Total Giveaways Held :</b> <code>{total_giveaways:,}</code>\n"
            f"🟢 <b>Live Giveaways :</b> <code>{live_giveaways:,}</code>\n"
            f"🔒 <b>Closed Giveaways :</b> <code>{closed_giveaways:,}</code>\n"
            f"📦 <b>Archived (Old) :</b> <code>{archived:,}</code>\n"
            f"🗳 <b>Total Votes Cast :</b> <code>{total_votes:,}</code>\n"
            f"🤖 <b>Active Clone Bots :</b> <code>{total_clones:,}</code>\n"
            f"🚫 <b>Banned Users :</b> <code>{banned_users:,}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Error fetching stats: <code>{e}</code>", parse_mode="HTML")


# ─── /db  ─────────────────────────────────────────────────────
# Shows total / used / free storage in MB for the live database.

@router.message(Command("db"))
async def cmd_db(message: Message):
    if not _is_superadmin(message.from_user.id):
        await message.answer("🚫 This command is for superadmins only.")
        return

    from utils.db import is_mongo, get_sqlite_path

    try:
        if is_mongo():
            from utils.db import get_db
            db_obj = get_db()
            stats  = await db_obj.command("dbStats", scale=1024 * 1024)
            total_mb    = round(stats.get("dataSize", 0) + stats.get("indexSize", 0), 2)
            storage_mb  = round(stats.get("storageSize", 0), 2)
            free_mb     = round(max(storage_mb - total_mb, 0), 2)

            # archive refs count
            archived = await db_obj.giveaway_archive_refs.count_documents({})
            await message.answer(
                "🗄 <b>Database Storage (MongoDB)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>Total Used :</b> <code>{total_mb} MB</code>\n"
                f"💾 <b>Storage Allocated :</b> <code>{storage_mb} MB</code>\n"
                f"🆓 <b>Free :</b> <code>{free_mb} MB</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📂 <b>Archived Giveaways :</b> <code>{archived}</code>\n\n"
                "ℹ️ Actual file archive is stored in your DATABASE_CHANNEL (Telegram).",
                parse_mode="HTML",
            )
        else:
            db_path = get_sqlite_path()
            if os.path.exists(db_path):
                used_bytes = os.path.getsize(db_path)
            else:
                used_bytes = 0
            # disk free for the partition
            st = os.statvfs(db_path if os.path.exists(db_path) else ".")
            free_bytes  = st.f_bavail * st.f_frsize
            total_bytes = st.f_blocks * st.f_frsize

            used_mb  = round(used_bytes / 1024 / 1024, 3)
            free_mb  = round(free_bytes / 1024 / 1024, 1)
            total_mb = round(total_bytes / 1024 / 1024, 1)

            import aiosqlite
            async with aiosqlite.connect(db_path) as conn:
                try:
                    async with conn.execute("SELECT COUNT(*) FROM giveaway_archive_refs") as cur:
                        archived = (await cur.fetchone())[0]
                except Exception:
                    archived = 0

            await message.answer(
                "🗄 <b>Database Storage (SQLite)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>Total DB Size :</b> <code>{used_mb} MB</code>\n"
                f"🆓 <b>Disk Free :</b> <code>{free_mb} MB</code>\n"
                f"💾 <b>Disk Total :</b> <code>{total_mb} MB</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📂 <b>Archived Giveaways :</b> <code>{archived}</code>\n\n"
                "ℹ️ Actual file archive is stored in your DATABASE_CHANNEL (Telegram).",
                parse_mode="HTML",
            )
    except Exception as e:
        await message.answer(f"❌ Error fetching DB info: <code>{e}</code>", parse_mode="HTML")


# ─── /getgiveaway <ID> ─────────────────────────────────────────

@router.message(Command("getgiveaway"))
async def cmd_get_giveaway(message: Message, bot: Bot):
    if not _is_superadmin(message.from_user.id):
        await message.answer("🚫 This command is for superadmins only.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer(
            "Usage: <code>/getgiveaway GIVEAWAY_ID</code>\n\n"
            "This retrieves the archived JSON from the DATABASE_CHANNEL.",
            parse_mode="HTML",
        )
        return

    giveaway_id = parts[1].upper()
    await _send_archived_file(bot, message.chat.id, giveaway_id)


# ─── /oldgiveaway ──────────────────────────────────────────────
# Superadmin: lists all archived giveaways.
# Creator: shows only their own archived giveaways.
# Anyone with an ID: /oldgiveaway <ID>

@router.message(Command("oldgiveaway"))
async def cmd_old_giveaway(message: Message, bot: Bot):
    parts     = message.text.strip().split()
    user_id   = message.from_user.id
    is_admin  = _is_superadmin(user_id)

    # ── /oldgiveaway <ID> — fetch specific file ────────────────
    if len(parts) >= 2:
        giveaway_id = parts[1].upper()
        # Verify access: admin OR creator of that giveaway
        if not is_admin:
            ok = await _user_owns_archive(user_id, giveaway_id)
            if not ok:
                await message.answer("🚫 You don't have access to this archived giveaway.")
                return
        await _send_archived_file(bot, message.chat.id, giveaway_id)
        return

    # ── /oldgiveaway — list ────────────────────────────────────
    from utils.giveaway_archive import get_old_giveaways
    all_old = await get_old_giveaways(limit=100)

    if not is_admin:
        all_old = [g for g in all_old if str(g.get("creator_id", "")) == str(user_id)]

    if not all_old:
        await message.answer(
            "📭 <b>No archived giveaways found.</b>\n\n"
            "Giveaways appear here after they are closed and archived.",
            parse_mode="HTML",
        )
        return

    lines = ["📦 <b>Old Giveaways</b>\n━━━━━━━━━━━━━━━━━━━━━"]
    for g in all_old[:20]:
        gid      = g.get("giveaway_id", "?")
        title    = g.get("title", "Unknown")[:35]
        created  = str(g.get("created_at", ""))[:10]
        ended    = str(g.get("end_date", ""))[:10]
        votes    = g.get("total_votes", 0)
        lines.append(
            f"\n🆔 <code>{gid}</code>\n"
            f"🏷 {title}\n"
            f"📅 Created: {created}  ⏰ Ended: {ended}\n"
            f"🗳 Votes: {votes}\n"
            f"📎 Use: <code>/oldgiveaway {gid}</code>"
        )

    if len(all_old) > 20:
        lines.append(f"\n…and {len(all_old) - 20} more. Use <code>/oldgiveaway ID</code> to fetch any.")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── /deleteold <months> ──────────────────────────────────────

@router.message(Command("deleteold"))
async def cmd_delete_old(message: Message):
    if not _is_superadmin(message.from_user.id):
        await message.answer("🚫 This command is for superadmins only.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Usage: <code>/deleteold &lt;months&gt;</code>\n\n"
            "Deletes archived giveaway <b>metadata</b> older than the specified number of months.\n"
            "Example: <code>/deleteold 3</code> — removes records older than 3 months.\n\n"
            "⚠️ The JSON files in DATABASE_CHANNEL are NOT deleted (Telegram keeps them).",
            parse_mode="HTML",
        )
        return

    months = int(parts[1])
    if months < 1:
        await message.answer("❌ Months must be at least 1.")
        return

    wait = await message.answer(f"🗑 Deleting archive records older than {months} month(s)…")
    from utils.giveaway_archive import delete_old_giveaways_before
    deleted = await delete_old_giveaways_before(months)
    try:
        await wait.delete()
    except Exception:
        pass
    await message.answer(
        f"✅ <b>Done!</b>\n\n"
        f"Removed <code>{deleted}</code> archived giveaway record(s) older than {months} month(s).\n\n"
        f"ℹ️ The actual JSON files in your DATABASE_CHANNEL are untouched.",
        parse_mode="HTML",
    )


# ─── Helpers ──────────────────────────────────────────────────

async def _send_archived_file(bot: Bot, chat_id: int, giveaway_id: str):
    from utils.db import get_db, is_mongo, get_sqlite_path
    file_id = None
    meta    = {}

    try:
        if is_mongo():
            doc = await get_db().giveaway_archive_refs.find_one({"giveaway_id": giveaway_id})
            if doc:
                file_id = doc.get("file_id")
                meta    = doc
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                try:
                    conn.row_factory = aiosqlite.Row
                    async with conn.execute(
                        "SELECT * FROM giveaway_archive_refs WHERE giveaway_id=?",
                        (giveaway_id,)
                    ) as cur:
                        row = await cur.fetchone()
                    if row:
                        meta    = dict(row)
                        file_id = meta.get("file_id")
                except Exception:
                    pass
    except Exception:
        pass

    if file_id:
        title    = meta.get("title", giveaway_id)
        created  = str(meta.get("created_at", ""))[:10]
        ended    = str(meta.get("end_date", ""))[:10]
        votes    = meta.get("total_votes", 0)
        await bot.send_document(
            chat_id,
            document=file_id,
            caption=(
                f"📦 <b>Archived Giveaway Data</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 <code>{giveaway_id}</code>\n"
                f"🏷 <b>Title:</b> {title}\n"
                f"📅 <b>Created:</b> {created}\n"
                f"⏰ <b>Ended:</b> {ended}\n"
                f"🗳 <b>Votes:</b> {votes}"
            ),
            parse_mode="HTML",
        )
    else:
        await bot.send_message(
            chat_id,
            f"❌ No archived file found for <code>{giveaway_id}</code>.\n\n"
            f"The archive JSON was sent to your DATABASE_CHANNEL when the giveaway closed.\n"
            f"Check the channel for <code>giveaway_{giveaway_id}.json</code>.",
            parse_mode="HTML",
        )


async def _user_owns_archive(user_id: int, giveaway_id: str) -> bool:
    """Check if user_id is the creator of the archived giveaway."""
    from utils.db import get_db, is_mongo, get_sqlite_path
    try:
        if is_mongo():
            doc = await get_db().giveaway_archive_refs.find_one({"giveaway_id": giveaway_id})
            return doc and str(doc.get("creator_id", "")) == str(user_id)
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                try:
                    async with conn.execute(
                        "SELECT creator_id FROM giveaway_archive_refs WHERE giveaway_id=?",
                        (giveaway_id,)
                    ) as cur:
                        row = await cur.fetchone()
                    return row and str(row[0]) == str(user_id)
                except Exception:
                    return False
    except Exception:
        return False


# ─── /broadcast ──────────────────────────────────────────────

def _broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yes, Send",  callback_data="bc:confirm"),
        InlineKeyboardButton(text="❌ Cancel",     callback_data="bc:cancel"),
    ]])


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not _is_superadmin(message.from_user.id):
        await message.answer("🚫 This command is for superadmins only.")
        return

    await state.set_state(BroadcastForm.waiting_message)
    await message.answer(
        "📢 <b>Broadcast to All Main-Bot Users</b>\n\n"
        "Send your message now (HTML supported).\n"
        "Example: <code>&lt;b&gt;🎉 Big update!&lt;/b&gt;</code>\n\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
    )


@router.message(Command("cancel"), BroadcastForm.waiting_message)
async def cmd_broadcast_cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Broadcast cancelled.")


@router.message(BroadcastForm.waiting_message)
async def broadcast_got_message(message: Message, state: FSMContext):
    text = message.html_text or message.text or ""
    if not text.strip():
        await message.answer("❌ Empty message, please send text.")
        return

    await state.update_data(bc_text=text)
    preview = text[:300] + ("…" if len(text) > 300 else "")
    await message.answer(
        f"📋 <b>Preview:</b>\n\n{preview}\n\n"
        f"Send this to <b>all main-bot users</b>?",
        parse_mode="HTML",
        reply_markup=_broadcast_confirm_keyboard(),
    )


@router.callback_query(F.data == "bc:cancel", BroadcastForm.waiting_message)
async def broadcast_cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("❌ Broadcast cancelled.")


@router.callback_query(F.data == "bc:confirm", BroadcastForm.waiting_message)
async def broadcast_cb_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    bc_text = data.get("bc_text", "")
    await state.clear()
    await callback.answer("📤 Sending…", show_alert=False)

    status_msg = await callback.message.edit_text(
        "📤 <b>Broadcast in progress…</b>\n\nThis may take a while for large user lists.",
        parse_mode="HTML",
    )

    from utils.db import get_db, is_mongo, get_sqlite_path
    from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

    user_ids: list[int] = []
    try:
        if is_mongo():
            async for u in get_db().main_bot_users.find({"is_banned": {"$ne": True}}, {"user_id": 1}):
                user_ids.append(u["user_id"])
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                async with conn.execute("SELECT user_id FROM main_bot_users WHERE is_banned=0") as cur:
                    user_ids = [r[0] for r in await cur.fetchall()]
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to fetch user list: <code>{e}</code>", parse_mode="HTML")
        return

    sent = failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, bc_text, parse_mode="HTML")
            sent += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"📨 Sent:   <code>{sent}</code>\n"
        f"❌ Failed: <code>{failed}</code>\n"
        f"👥 Total:  <code>{len(user_ids)}</code>",
        parse_mode="HTML",
    )
