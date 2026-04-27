# handlers/giveaway.py
import asyncio
import html
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger(__name__)
from models.giveaway import (
    create_giveaway, get_giveaway, record_vote, record_vote_unlimited,
    close_giveaway, update_giveaway_message_id
)
from utils.poll_renderer import render_giveaway_message, build_vote_keyboard, build_verify_join_keyboard
from utils.premium import is_premium

router = Router()


class GiveawayForm(StatesGroup):
    channel_id     = State()
    title          = State()
    prizes         = State()
    options        = State()
    end_time       = State()
    winner_dm      = State()   # ask creator if they want winner auto-DM
    confirm        = State()


# ─── Shared keyboards ─────────────────────────────────────────

def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="giveaway_cancel")]
    ])


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Post Giveaway", callback_data="giveaway_confirm:yes"),
            InlineKeyboardButton(text="❌ Cancel",        callback_data="giveaway_confirm:no"),
        ]
    ])


def _winner_dm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, DM the winner",  callback_data="winnerdm:yes")],
        [InlineKeyboardButton(text="❌ No, skip DM",         callback_data="winnerdm:no")],
        [InlineKeyboardButton(text="🚫 Cancel",              callback_data="giveaway_cancel")],
    ])


def _end_time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Yes, set end time", callback_data="endtime:yes")],
        [InlineKeyboardButton(text="⏭ No end time",       callback_data="endtime:no")],
        [InlineKeyboardButton(text="❌ Cancel",            callback_data="giveaway_cancel")],
    ])


def _parse_end_time(text: str):
    text = text.strip().lower()
    try:
        if text.endswith("h"):
            return datetime.utcnow() + timedelta(hours=float(text[:-1]))
        elif text.endswith("m"):
            return datetime.utcnow() + timedelta(minutes=float(text[:-1]))
        elif text.endswith("d"):
            return datetime.utcnow() + timedelta(days=float(text[:-1]))
    except ValueError:
        pass
    return None


# ─── Cancel (anywhere in the flow) ───────────────────────────

@router.callback_query(F.data == "giveaway_cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    logger.info(f"[GIVEAWAY] handle_cancel: user={callback.from_user.id} cancelled giveaway creation")
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Giveaway creation cancelled.</b>\n\n"
        "Tap /creategiveaway whenever you're ready to start again.",
        parse_mode="HTML",
    )


# ─── Create Giveaway ──────────────────────────────────────────

@router.message(Command("creategiveaway"))
@router.callback_query(F.data == "menu:create_giveaway")
@router.callback_query(F.data == "menu:create_giveaway_poll")
async def start_create_giveaway(event, state: FSMContext, bot: Bot):
    msg    = event if isinstance(event, Message) else event.message
    user   = event.from_user
    if isinstance(event, CallbackQuery):
        await event.answer()

    logger.info(f"[GIVEAWAY] start_create_giveaway triggered by user={user.id} username=@{user.username}")
    await state.set_state(GiveawayForm.channel_id)
    logger.info(f"[GIVEAWAY] State set to channel_id for user={user.id}")
    await msg.answer(
        "🗳 <b>Create a Giveaway Poll</b>\n\n"
        "<b>Step 1 of 5 — Channel</b>\n\n"
        "Enter your channel username:\n"
        "Example: <code>@mychannel</code>\n\n"
        "⚠️ Make sure the bot is already an <b>admin</b> in that channel!",
        parse_mode="HTML",
        reply_markup=_cancel_keyboard(),
    )


@router.message(GiveawayForm.channel_id)
async def form_channel_id(message: Message, state: FSMContext, bot: Bot):
    channel = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"[GIVEAWAY] form_channel_id: user={user_id} entered channel={channel}")

    if not channel.startswith("@") and not channel.lstrip("-").isdigit():
        logger.warning(f"[GIVEAWAY] form_channel_id: invalid format user={user_id} input={channel}")
        await message.answer(
            "❌ Please enter a valid channel like @mychannel",
            reply_markup=_cancel_keyboard(),
        )
        return

    # Try to resolve chat ID — but never block the user if it fails
    chat_id = channel
    chat_title = channel
    try:
        chat = await bot.get_chat(channel)
        chat_id = str(chat.id)
        chat_title = chat.title or channel
        logger.info(f"[GIVEAWAY] form_channel_id: resolved chat_id={chat_id} title={chat_title}")
    except Exception as e:
        logger.warning(f"[GIVEAWAY] form_channel_id: get_chat failed ({e}), using raw input as chat_id")

    await state.update_data(
        channel_id=chat_id,
        channel_username=channel,
        channel_title=chat_title,
    )
    await state.set_state(GiveawayForm.title)
    logger.info(f"[GIVEAWAY] form_channel_id: proceeding to title state for user={user_id}")
    await message.answer(
        "✅ Channel saved!\n\n"
        "Step 2 of 5 — Giveaway Title\n\n"
        "Enter the title for your giveaway:\n"
        "Example: iPhone 15 Giveaway",
        reply_markup=_cancel_keyboard(),
    )


@router.message(GiveawayForm.title)
async def form_title(message: Message, state: FSMContext):
    logger.info(f"[GIVEAWAY] form_title: user={message.from_user.id} title={message.text.strip()[:50]}")
    await state.update_data(title=message.text.strip())
    await state.set_state(GiveawayForm.prizes)
    await message.answer(
        "<b>Step 3 of 5 — Prizes</b>\n\n"
        "Enter the <b>prizes</b> — one per line:\n\n"
        "Example:\n"
        "<code>₹100 Dominos Gift Card\n"
        "Myntra ₹100 Coupon</code>",
        parse_mode="HTML",
        reply_markup=_cancel_keyboard(),
    )


@router.message(GiveawayForm.prizes)
async def form_prizes(message: Message, state: FSMContext):
    logger.info(f"[GIVEAWAY] form_prizes: user={message.from_user.id}")
    prizes = [p.strip() for p in message.text.strip().split("\n") if p.strip()]
    if not prizes:
        await message.answer(
            "❌ Enter at least one prize.",
            reply_markup=_cancel_keyboard(),
        )
        return
    await state.update_data(prizes=prizes)
    await state.set_state(GiveawayForm.options)
    await message.answer(
        "<b>Step 4 of 5 — Poll Options</b>\n\n"
        "Enter <b>participant names / poll options</b> — one per line:\n\n"
        "Example:\n"
        "<code>Royality\nDev Goyal\nKranthi C\nEmon</code>",
        parse_mode="HTML",
        reply_markup=_cancel_keyboard(),
    )


@router.message(GiveawayForm.options)
async def form_options(message: Message, state: FSMContext):
    logger.info(f"[GIVEAWAY] form_options: user={message.from_user.id}")
    options = [o.strip() for o in message.text.strip().split("\n") if o.strip()]
    if len(options) < 2:
        await message.answer(
            "❌ Enter at least 2 options.",
            reply_markup=_cancel_keyboard(),
        )
        return
    if len(options) > 50:
        await message.answer(
            "❌ Maximum 50 options allowed.",
            reply_markup=_cancel_keyboard(),
        )
        return
    await state.update_data(options=options)
    await state.set_state(GiveawayForm.end_time)
    await message.answer(
        "<b>Step 5 of 5 — End Time</b>\n\n"
        "Would you like to set an <b>end time</b> for this poll?",
        parse_mode="HTML",
        reply_markup=_end_time_keyboard(),
    )


@router.callback_query(F.data.startswith("endtime:"))
async def handle_endtime_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    choice = callback.data.split(":")[1]
    if choice == "no":
        await state.update_data(end_time=None)
    else:
        await callback.message.answer(
            "⏰ <b>Enter how long the poll should run:</b>\n\n"
            "Examples:\n"
            "<code>2h</code>  → 2 hours\n"
            "<code>30m</code> → 30 minutes\n"
            "<code>1d</code>  → 1 day",
            parse_mode="HTML",
            reply_markup=_cancel_keyboard(),
        )
        return
    # Ask about winner DM
    await state.set_state(GiveawayForm.winner_dm)
    await callback.message.answer(
        "🎉 <b>Winner Auto-DM</b>\n\n"
        "Should the bot automatically DM the top-voted winner "
        "when this giveaway ends?",
        parse_mode="HTML",
        reply_markup=_winner_dm_keyboard(),
    )


@router.message(GiveawayForm.end_time)
async def form_end_time(message: Message, state: FSMContext):
    end_time = _parse_end_time(message.text)
    if not end_time:
        await message.answer(
            "❌ Invalid format. Use <code>2h</code>, <code>30m</code>, or <code>1d</code>",
            parse_mode="HTML",
            reply_markup=_cancel_keyboard(),
        )
        return
    await state.update_data(end_time=end_time)
    # Ask about winner DM
    await state.set_state(GiveawayForm.winner_dm)
    await message.answer(
        "🎉 <b>Winner Auto-DM</b>\n\n"
        "Should the bot automatically DM the top-voted winner "
        "when this giveaway ends?",
        parse_mode="HTML",
        reply_markup=_winner_dm_keyboard(),
    )


@router.callback_query(F.data.startswith("winnerdm:"))
async def handle_winner_dm_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    allow = callback.data.split(":")[1] == "yes"
    await state.update_data(allow_winner_dm=allow)
    await _show_preview(callback.message, state)


async def _show_preview(msg: Message, state: FSMContext):
    await state.set_state(GiveawayForm.confirm)
    data = await state.get_data()
    options = data["options"]
    prizes  = data["prizes"]

    prizes_preview = "\n".join([
        f"  {'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else f'{i+1}.'} {p}"
        for i, p in enumerate(prizes)
    ])
    options_preview = "\n".join([f"  • {o}" for o in options[:5]])
    if len(options) > 5:
        options_preview += f"\n  … and {len(options)-5} more"

    end_str = ""
    if data.get("end_time"):
        end_str = f"\n⏰ <b>Ends:</b> {data['end_time'].strftime('%Y-%m-%d %H:%M')} UTC"

    await msg.answer(
        "👀 <b>Preview — Review before posting</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>Channel:</b> {data['channel_username']}\n"
        f"🏷 <b>Title:</b> {data['title']}{end_str}\n\n"
        f"🎁 <b>Prizes:</b>\n{prizes_preview}\n\n"
        f"🗳 <b>Options ({len(options)}):</b>\n{options_preview}",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(F.data.startswith("giveaway_confirm:"))
async def handle_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.info(f"[GIVEAWAY] handle_confirm: user={callback.from_user.id} choice={callback.data}")
    await callback.answer()
    choice = callback.data.split(":")[1]

    if choice == "no":
        await state.clear()
        await callback.message.edit_text(
            "❌ <b>Giveaway cancelled.</b>\n\nUse /creategiveaway to start a new one.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    await state.clear()

    giveaway = await create_giveaway(
        creator_id=callback.from_user.id,
        channel_id=data["channel_id"],
        title=data["title"],
        prizes=data["prizes"],
        options=data["options"],
        end_time=data.get("end_time"),
        allow_winner_dm=data.get("allow_winner_dm", False),
    )

    _creator_premium = await is_premium(callback.from_user.id)
    text     = render_giveaway_message(
        title=data["title"], prizes=data["prizes"],
        options=data["options"], votes={},
        total_votes=0, is_active=True,
        end_time=data.get("end_time"),
        hide_stamp=_creator_premium,
    )
    keyboard = build_vote_keyboard(giveaway["giveaway_id"], data["options"], is_active=True)

    try:
        sent = await bot.send_message(data["channel_id"], text, reply_markup=keyboard, parse_mode="HTML")
        await update_giveaway_message_id(giveaway["giveaway_id"], sent.message_id, data["channel_id"])

        # Analytics panel
        from models.panel import create_panel
        from config.settings import settings
        try:
            chat         = await bot.get_chat(data["channel_id"])
            member_count = await bot.get_chat_member_count(data["channel_id"])
            channel_title = chat.title or data.get("channel_username", "")
        except Exception:
            member_count  = 0
            channel_title = data.get("channel_username", "")

        panel = await create_panel(
            owner_id=callback.from_user.id,
            panel_type="giveaway",
            ref_id=giveaway["giveaway_id"],
            channel_id=data["channel_id"],
            channel_username=data.get("channel_username", ""),
            channel_title=channel_title,
            member_count_start=member_count,
        )

        # ── Fix: build URL without double-https ──────────────
        domain   = settings.WEB_DOMAIN.lstrip("https://").lstrip("http://")
        panel_url = f"https://{domain}/panel/{panel['token']}"

        # ── Build share URL (message link if public channel, else referral) ──
        try:
            chat_obj = await bot.get_chat(data["channel_id"])
            if chat_obj.username:
                share_url = f"https://t.me/{chat_obj.username}/{sent.message_id}"
            else:
                # private channel — use bot referral link instead
                me_info = await bot.get_me()
                share_url = f"https://t.me/{me_info.username}?start=ga_{giveaway['giveaway_id']}"
        except Exception:
            me_info   = await bot.get_me()
            share_url = f"https://t.me/{me_info.username}?start=ga_{giveaway['giveaway_id']}"

        tg_share_url = f"https://t.me/share/url?url={share_url}&text=Join+this+giveaway+and+vote+now!"

        dm_status = "✅ Winner will be auto-DM'd" if data.get("allow_winner_dm") else "❌ Winner DM disabled"

        await callback.message.edit_text(
            f"✅ <b>Giveaway posted successfully!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{giveaway['giveaway_id']}</code>\n"
            f"🎉 <b>Winner DM:</b> {dm_status}\n\n"
            f"📊 <b>Your Analytics Panel:</b>\n"
            f"<a href=\"{panel_url}\">{panel_url}</a>\n\n"
            f"To close the poll manually, tap below:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔒 Close Poll",
                    callback_data=f"close_poll:{giveaway['giveaway_id']}",
                )],
                [InlineKeyboardButton(text="📊 View Analytics", url=panel_url)],
                [InlineKeyboardButton(text="🔗 Share Giveaway", url=tg_share_url)],
            ]),
        )

        if data.get("end_time"):
            delay = (data["end_time"] - datetime.utcnow()).total_seconds()
            if delay > 0:
                asyncio.create_task(_auto_close(giveaway["giveaway_id"], delay, bot))

    except Exception as e:
        await callback.message.edit_text(
            f"❌ <b>Failed to post giveaway.</b>\n\n"
            f"<code>{e}</code>",
            parse_mode="HTML",
        )


async def _auto_close(giveaway_id: str, delay: float, bot: Bot):
    await asyncio.sleep(delay)
    giveaway = await get_giveaway(giveaway_id)
    if not giveaway or not giveaway["is_active"]:
        return
    await close_giveaway(giveaway_id)
    updated = await get_giveaway(giveaway_id)
    votes   = {int(k): v for k, v in updated.get("votes", {}).items()}
    text    = render_giveaway_message(
        title=updated["title"], prizes=updated["prizes"],
        options=updated["options"], votes=votes,
        total_votes=updated["total_votes"], is_active=False,
    )
    try:
        await bot.edit_message_text(
            text, chat_id=updated["channel_id"],
            message_id=updated["message_id"], parse_mode="HTML",
        )
    except Exception:
        pass
    await _send_close_report(bot, updated, votes)
    await _dm_winner_if_allowed(bot, updated, votes)
    await _archive_giveaway(bot, giveaway_id, creator_id=giveaway.get("creator_id"))


async def _dm_winner_if_allowed(bot: Bot, giveaway: dict, votes: dict):
    """
    Auto-DM the top-voted option winner if the giveaway creator allowed it.
    The winner must have voted so we can look up their user_id from the votes table.
    """
    if not giveaway.get("allow_winner_dm", False):
        return
    options = giveaway.get("options", [])
    total   = giveaway.get("total_votes", 0)
    if not options or total == 0:
        return

    # Find top option index
    top_idx = max(range(len(options)), key=lambda i: votes.get(i, 0))
    top_name = options[top_idx]

    # Look up who voted for this option
    from utils.db import get_db, is_mongo, get_sqlite_path
    winner_user_id = None
    try:
        if is_mongo():
            doc = await get_db().votes.find_one(
                {"giveaway_id": giveaway["giveaway_id"], "option_index": top_idx}
            )
            if doc:
                winner_user_id = doc.get("user_id")
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                async with conn.execute(
                    "SELECT user_id FROM votes WHERE giveaway_id=? AND option_index=? LIMIT 1",
                    (giveaway["giveaway_id"], top_idx)
                ) as cur:
                    row = await cur.fetchone()
                if row:
                    winner_user_id = row[0]
    except Exception:
        pass

    prizes = giveaway.get("prizes", [])
    prize  = prizes[0] if prizes else "the prize"

    try:
        if winner_user_id:
            await bot.send_message(
                winner_user_id,
                f"🎉 <b>Congratulations!</b>\n\n"
                f"You won the giveaway <b>{giveaway['title']}</b>!\n\n"
                f"🏆 <b>Prize:</b> {prize}\n\n"
                f"The giveaway creator will contact you shortly.",
                parse_mode="HTML",
            )
    except Exception:
        pass  # User may have blocked the bot


async def _archive_giveaway(bot: Bot, giveaway_id: str, creator_id: int = None):
    """Archive closed giveaway to DATABASE_CHANNEL and purge from live DB."""
    from config.settings import settings
    from utils.log_utils import get_main_bot

    # Always use the main bot — clone bots are not admins in DATABASE_CHANNEL
    notify_bot = get_main_bot() or bot

    async def _notify_creator(msg: str):
        if creator_id:
            try:
                await notify_bot.send_message(creator_id, msg, parse_mode="HTML")
            except Exception:
                pass

    if not getattr(settings, "DATABASE_CHANNEL", None):
        logger.warning("_archive_giveaway: DATABASE_CHANNEL not set — skipping archive")
        await _notify_creator(
            "⚠️ <b>Giveaway data not archived!</b>\n\n"
            "The <code>DATABASE_CHANNEL</code> env variable is not set.\n"
            "Your giveaway data was <b>not save
