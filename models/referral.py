import json
from datetime import datetime
from typing import Optional, List


def _now() -> str:
    return datetime.utcnow().isoformat()


# ══════════════════════════════════════════════════════════════
# CLONE BOT
# ══════════════════════════════════════════════════════════════

async def _mongo_create_clone(owner_id, token, bot_username, welcome_message, channel_link, referral_caption, enabled_commands):
    from utils.db import get_db
    clone = {
        "owner_id": owner_id, "token": token,
        "bot_username": bot_username, "welcome_message": welcome_message,
        "channel_link": channel_link,
        "referral_caption": referral_caption,
        "enabled_commands": enabled_commands,
        "is_active": True, "is_banned": False,
        "created_at": datetime.utcnow()
    }
    await get_db().clone_bots.insert_one(clone)
    return clone


async def _mongo_get_clone(token):
    from utils.db import get_db
    return await get_db().clone_bots.find_one({"token": token})


async def _mongo_get_clone_by_owner(owner_id):
    from utils.db import get_db
    return await get_db().clone_bots.find_one({"owner_id": owner_id, "is_active": True})


async def _mongo_get_all_clones():
    from utils.db import get_db
    return await get_db().clone_bots.find({"is_active": True, "is_banned": False}).to_list(length=None)


async def _mongo_ban_clone(token):
    from utils.db import get_db
    await get_db().clone_bots.update_one({"token": token}, {"$set": {"is_banned": True}})


async def _mongo_delete_clone(owner_id):
    from utils.db import get_db
    await get_db().clone_bots.update_one({"owner_id": owner_id}, {"$set": {"is_active": False}})


async def _mongo_update_clone(token, **fields):
    from utils.db import get_db
    await get_db().clone_bots.update_one({"token": token}, {"$set": fields})


async def _sqlite_create_clone(owner_id, token, bot_username, welcome_message, channel_link, referral_caption, enabled_commands):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute(
            """INSERT OR IGNORE INTO clone_bots
               (owner_id, token, bot_username, welcome_message, channel_link,
                referral_caption, enabled_commands, is_active, is_banned, created_at)
               VALUES (?,?,?,?,?,?,?,1,0,?)""",
            (owner_id, token, bot_username, welcome_message, channel_link,
             referral_caption, json.dumps(enabled_commands), _now())
        )
        await conn.commit()
    return await _sqlite_get_clone(token)


async def _sqlite_get_clone(token):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM clone_bots WHERE token=?", (token,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("enabled_commands"), str):
        d["enabled_commands"] = json.loads(d["enabled_commands"])
    return d


async def _sqlite_get_clone_by_owner(owner_id):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM clone_bots WHERE owner_id=? AND is_active=1", (owner_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("enabled_commands"), str):
        d["enabled_commands"] = json.loads(d["enabled_commands"])
    return d


async def _sqlite_get_all_clones():
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM clone_bots WHERE is_active=1 AND is_banned=0"
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("enabled_commands"), str):
            d["enabled_commands"] = json.loads(d["enabled_commands"])
        result.append(d)
    return result


async def _sqlite_ban_clone(token):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute("UPDATE clone_bots SET is_banned=1 WHERE token=?", (token,))
        await conn.commit()


async def _sqlite_delete_clone(owner_id):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute("UPDATE clone_bots SET is_active=0 WHERE owner_id=?", (owner_id,))
        await conn.commit()


async def _sqlite_update_clone(token, **fields):
    import aiosqlite
    from utils.db import get_sqlite_path
    if "enabled_commands" in fields:
        fields["enabled_commands"] = json.dumps(fields["enabled_commands"])
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [token]
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute(f"UPDATE clone_bots SET {sets} WHERE token=?", vals)
        await conn.commit()


# ══════════════════════════════════════════════════════════════
# REFERRALS
# ══════════════════════════════════════════════════════════════

async def _mongo_add_referral(clone_token, user_id, user_name, referred_by, lang="en"):
    from utils.db import get_db
    db = get_db()
    if await db.referrals.find_one({"clone_token": clone_token, "user_id": user_id}):
        return False
    await db.referrals.insert_one({
        "clone_token": clone_token, "user_id": user_id,
        "user_name": user_name, "referred_by": referred_by,
        "refer_count": 0, "lang": lang,
        "joined_at": datetime.utcnow()
    })
    if referred_by:
        await db.referrals.update_one(
            {"clone_token": clone_token, "user_id": referred_by},
            {"$inc": {"refer_count": 1}}
        )
    return True


async def _mongo_get_referral_user(clone_token, user_id):
    from utils.db import get_db
    return await get_db().referrals.find_one({"clone_token": clone_token, "user_id": user_id})


async def _mongo_update_user_lang(clone_token, user_id, lang):
    from utils.db import get_db
    await get_db().referrals.update_one(
        {"clone_token": clone_token, "user_id": user_id},
        {"$set": {"lang": lang}}
    )


async def _mongo_reset_referral(clone_token, user_id):
    from utils.db import get_db
    await get_db().referrals.update_one(
        {"clone_token": clone_token, "user_id": user_id},
        {"$set": {"refer_count": 0}}
    )


async def _mongo_get_leaderboard(clone_token, page, per_page):
    from utils.db import get_db
    total = await get_db().referrals.count_documents({"clone_token": clone_token})
    skip = (page - 1) * per_page
    cursor = get_db().referrals.find({"clone_token": clone_token}).sort("refer_count", -1).skip(skip).limit(per_page)
    return await cursor.to_list(length=per_page), total


async def _mongo_get_all_users(clone_token):
    from utils.db import get_db
    return await get_db().referrals.find({"clone_token": clone_token}).to_list(length=None)


async def _mongo_get_top(clone_token):
    from utils.db import get_db
    results = await get_db().referrals.find({"clone_token": clone_token}).sort("refer_count", -1).limit(1).to_list(1)
    return results[0] if results else None


async def _mongo_get_referred_by_user(clone_token, referrer_id):
    from utils.db import get_db
    return await get_db().referrals.find(
        {"clone_token": clone_token, "referred_by": referrer_id}
    ).to_list(length=None)


async def _mongo_get_daily_joins(clone_token):
    from utils.db import get_db
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(days=7)
    cursor = get_db().referrals.find(
        {"clone_token": clone_token, "joined_at": {"$gte": since}}
    )
    return await cursor.to_list(length=None)


# ── SQLite referral helpers ───────────────────────────────────

async def _sqlite_add_referral(clone_token, user_id, user_name, referred_by, lang="en"):
    import aiosqlite
    from utils.db import get_sqlite_path
    path = get_sqlite_path()
    async with aiosqlite.connect(path) as conn:
        async with conn.execute(
            "SELECT id FROM referrals WHERE clone_token=? AND user_id=?",
            (clone_token, user_id)
        ) as cur:
            if await cur.fetchone():
                return False
        await conn.execute(
            """INSERT INTO referrals
               (clone_token, user_id, user_name, referred_by, refer_count, lang, joined_at)
               VALUES (?,?,?,?,0,?,?)""",
            (clone_token, user_id, user_name, referred_by, lang, _now())
        )
        if referred_by:
            await conn.execute(
                "UPDATE referrals SET refer_count=refer_count+1 WHERE clone_token=? AND user_id=?",
                (clone_token, referred_by)
            )
        await conn.commit()
    return True


async def _sqlite_get_referral_user(clone_token, user_id):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM referrals WHERE clone_token=? AND user_id=?",
            (clone_token, user_id)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def _sqlite_update_user_lang(clone_token, user_id, lang):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute(
            "UPDATE referrals SET lang=? WHERE clone_token=? AND user_id=?",
            (lang, clone_token, user_id)
        )
        await conn.commit()


async def _sqlite_reset_referral(clone_token, user_id):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute(
            "UPDATE referrals SET refer_count=0 WHERE clone_token=? AND user_id=?",
            (clone_token, user_id)
        )
        await conn.commit()


async def _sqlite_get_leaderboard(clone_token, page, per_page):
    import aiosqlite
    from utils.db import get_sqlite_path
    path = get_sqlite_path()
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE clone_token=?", (clone_token,)
        ) as cur:
            total = (await cur.fetchone())[0]
        skip = (page - 1) * per_page
        async with conn.execute(
            "SELECT * FROM referrals WHERE clone_token=? ORDER BY refer_count DESC LIMIT ? OFFSET ?",
            (clone_token, per_page, skip)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows], total


async def _sqlite_get_all_users(clone_token):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM referrals WHERE clone_token=?", (clone_token,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _sqlite_get_top(clone_token):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM referrals WHERE clone_token=? ORDER BY refer_count DESC LIMIT 1",
            (clone_token,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def _sqlite_get_referred_by_user(clone_token, referrer_id):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM referrals WHERE clone_token=? AND referred_by=?",
            (clone_token, referrer_id)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _sqlite_get_daily_joins(clone_token):
    import aiosqlite
    from utils.db import get_sqlite_path
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM referrals WHERE clone_token=? AND joined_at >= ?",
            (clone_token, since)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

DEFAULT_COMMANDS = ["refer", "mystats", "leaderboard", "myreferrals"]


async def create_clone_bot(owner_id, token, bot_username, welcome_message,
                            channel_link="", referral_caption="", enabled_commands=None):
    from utils.db import is_mongo
    if enabled_commands is None:
        enabled_commands = DEFAULT_COMMANDS
    if is_mongo():
        return await _mongo_create_clone(owner_id, token, bot_username, welcome_message,
                                          channel_link, referral_caption, enabled_commands)
    return await _sqlite_create_clone(owner_id, token, bot_username, welcome_message,
                                       channel_link, referral_caption, enabled_commands)


async def get_clone_bot(token):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_clone(token)
    return await _sqlite_get_clone(token)


async def get_clone_bot_by_owner(owner_id):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_clone_by_owner(owner_id)
    return await _sqlite_get_clone_by_owner(owner_id)


async def get_all_clone_bots():
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_all_clones()
    return await _sqlite_get_all_clones()


async def ban_clone_bot(token):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_ban_clone(token)
    return await _sqlite_ban_clone(token)


async def delete_clone_bot(owner_id):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_delete_clone(owner_id)
    return await _sqlite_delete_clone(owner_id)


async def update_clone_bot(token, **fields):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_update_clone(token, **fields)
    return await _sqlite_update_clone(token, **fields)


async def add_referral_user(clone_token, user_id, user_name, referred_by=None, lang="en"):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_add_referral(clone_token, user_id, user_name, referred_by, lang)
    return await _sqlite_add_referral(clone_token, user_id, user_name, referred_by, lang)


async def get_referral_user(clone_token, user_id):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_referral_user(clone_token, user_id)
    return await _sqlite_get_referral_user(clone_token, user_id)


async def update_user_lang(clone_token, user_id, lang):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_update_user_lang(clone_token, user_id, lang)
    return await _sqlite_update_user_lang(clone_token, user_id, lang)


async def reset_referral_count(clone_token, user_id):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_reset_referral(clone_token, user_id)
    return await _sqlite_reset_referral(clone_token, user_id)


async def get_leaderboard(clone_token, page=1, per_page=20):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_leaderboard(clone_token, page, per_page)
    return await _sqlite_get_leaderboard(clone_token, page, per_page)


async def get_all_users_for_clone(clone_token):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_all_users(clone_token)
    return await _sqlite_get_all_users(clone_token)


async def get_top_referrer(clone_token):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_top(clone_token)
    return await _sqlite_get_top(clone_token)


async def get_referred_by_user(clone_token, referrer_id):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_referred_by_user(clone_token, referrer_id)
    return await _sqlite_get_referred_by_user(clone_token, referrer_id)


async def get_daily_joins(clone_token):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_daily_joins(clone_token)
    return await _sqlite_get_daily_joins(clone_token)


async def update_referral_source(clone_token: str, user_id: int, new_referrer_id: int):
    """
    Credit a referral to new_referrer_id for user_id (used when an existing user
    clicks a fresh referral link). Increments referrer's refer_count by 1.
    """
    from utils.db import get_db, is_mongo, get_sqlite_path
    if is_mongo():
        db = get_db()
        await db.referrals.update_one(
            {"clone_token": clone_token, "user_id": user_id},
            {"$set": {"referred_by": new_referrer_id}}
        )
        await db.referrals.update_one(
            {"clone_token": clone_token, "user_id": new_referrer_id},
            {"$inc": {"refer_count": 1}}
        )
    else:
        import aiosqlite
        async with aiosqlite.connect(get_sqlite_path()) as conn:
            await conn.execute(
                "UPDATE referrals SET referred_by=? WHERE clone_token=? AND user_id=?",
                (new_referrer_id, clone_token, user_id)
            )
            await conn.execute(
                "UPDATE referrals SET refer_count=refer_count+1 WHERE clone_token=? AND user_id=?",
                (clone_token, new_referrer_id)
            )
            await conn.commit()
