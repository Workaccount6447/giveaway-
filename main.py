import asyncio
import logging
import json
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config.settings import settings
from handlers import start, giveaway, referral, admin, clone_bot
from utils.db import init_db
from utils.clone_manager import get_clone_manager
import utils.clone_manager as clone_manager_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ─── Poll restore on restart ──────────────────────────────────

async def _restore_active_polls(bot: Bot):
    from utils.db import get_db, is_mongo, get_sqlite_path
    from utils.poll_renderer import render_giveaway_message, build_vote_keyboard
    await asyncio.sleep(3)
    try:
        if is_mongo():
            db = get_db()
            polls = await db.giveaways.find(
                {"is_active": True, "message_id": {"$ne": None}}
            ).to_list(length=None)
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM giveaways WHERE is_active=1 AND message_id IS NOT NULL"
                ) as cur:
                    rows = await cur.fetchall()
            polls = []
            for r in rows:
                d = dict(r)
                d["prizes"]  = json.loads(d["prizes"])
                d["options"] = json.loads(d["options"])
                d["votes"]   = json.loads(d["votes"])
                d["is_active"] = bool(d["is_active"])
                polls.append(d)

        restored = 0
        for poll in polls:
            try:
                votes = {int(k): v for k, v in poll.get("votes", {}).items()}
                text = render_giveaway_message(
                    title=poll["title"], prizes=poll["prizes"],
                    options=poll["options"], votes=votes,
                    total_votes=poll["total_votes"], is_active=True
                )
                keyboard = build_vote_keyboard(
                    poll["giveaway_id"], poll["options"], is_active=True
                )
                await bot.edit_message_text(
                    text, chat_id=poll["channel_id"],
                    message_id=poll["message_id"],
                    reply_markup=keyboard, parse_mode="HTML"
                )
                restored += 1
                await asyncio.sleep(0.3)
            except Exception:
                pass
        if restored:
            logger.info(f"✅ Restored {restored} active poll(s) after restart")
    except Exception as e:
        logger.error(f"Poll restore error: {e}")


# ─── Bot startup (runs after DB is ready) ─────────────────────

async def _start_bot():
    try:
        storage = MemoryStorage()
        bot = Bot(token=settings.BOT_TOKEN)
        dp  = Dispatcher(storage=storage)

        me = await bot.get_me()
        clone_manager_module.MAIN_BOT_USERNAME = me.username
        logger.info(f"🤖 Main bot: @{me.username}")

        from web.broadcaster import set_main_bot
        set_main_bot(bot)

        dp.include_router(start.router)
        dp.include_router(giveaway.router)
        dp.include_router(referral.router)
        dp.include_router(admin.router)
        dp.include_router(clone_bot.router)

        clone_manager = get_clone_manager()
        asyncio.create_task(clone_manager.start_all_clones())
        asyncio.create_task(_restore_active_polls(bot))

        from utils.snapshot_scheduler import set_bot as set_snap_bot, snapshot_loop
        set_snap_bot(bot)
        asyncio.create_task(snapshot_loop())

        from utils.keep_alive import set_domain, keep_alive_loop
        set_domain(settings.WEB_DOMAIN)
        asyncio.create_task(keep_alive_loop())

        logger.info("🚀 Bot polling started!")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member"]
        )
    except Exception as e:
        logger.error(f"❌ Bot failed: {e}", exc_info=True)


# ─── DB init then launch bot (background task) ────────────────

async def _init_then_start_bot():
    """Runs in background so uvicorn can bind port first."""
    try:
        logger.info("🔄 Initialising database...")
        await init_db()
        logger.info("✅ Database ready — starting bot")
        await _start_bot()
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)


# ─── Main ─────────────────────────────────────────────────────

async def main():
    import uvicorn
    from web.app import app as fastapi_app

    uvi_config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=settings.WEB_PORT,
        log_level="warning",
        loop="none",   # share the already-running asyncio loop
    )
    uvi_server = uvicorn.Server(uvi_config)

    # Start DB init + bot in background — uvicorn binds port immediately
    # so Render detects it without waiting for MongoDB retries
    asyncio.create_task(_init_then_start_bot())

    logger.info(f"🌐 Web server binding on port {settings.WEB_PORT}...")
    await uvi_server.serve()   # blocks here; bot runs as background task


if __name__ == "__main__":
    asyncio.run(main())
