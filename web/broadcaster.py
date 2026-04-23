"""Global broadcast helper called from the web panel."""
import asyncio
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)
_main_bot: Bot = None

def set_main_bot(bot: Bot):
    global _main_bot
    _main_bot = bot

async def do_global_broadcast(message: str):
    if not _main_bot:
        logger.error("Broadcast: main bot not set")
        return
    from models.referral import get_all_users_for_clone, get_all_clone_bots
    clones = await get_all_clone_bots()
    seen = set()
    sent = failed = 0
    for clone in clones:
        users = await get_all_users_for_clone(clone["token"])
        for u in users:
            uid = u["user_id"]
            if uid in seen:
                continue
            seen.add(uid)
            try:
                await _main_bot.send_message(
                    uid, f"📢 <b>Announcement</b>\n\n{message}", parse_mode="HTML"
                )
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
    logger.info(f"Global broadcast done: {sent} sent, {failed} failed")
