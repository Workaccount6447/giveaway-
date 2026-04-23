"""
Panel model — stores user panel data for giveaway and refer bots.
Each panel has a unique random token (URL key).
"""
import secrets
import json
from datetime import datetime
from typing import Optional


def _now(): return datetime.utcnow().isoformat()
def _gen_token(): return secrets.token_urlsafe(24)


# ══════════════════════════════════════════════════════════════
# MONGO
# ══════════════════════════════════════════════════════════════

async def _mongo_create_panel(owner_id, panel_type, ref_id, channel_id, channel_username,
                               channel_title, member_count_start):
    from utils.db import get_db
    token = _gen_token()
    doc = {
        "token": token,
        "owner_id": owner_id,
        "panel_type": panel_type,   # "giveaway" | "refer"
        "ref_id": ref_id,           # giveaway_id or clone_token
        "channel_id": channel_id,
        "channel_username": channel_username,
        "channel_title": channel_title,
        "member_snapshots": [{"t": _now(), "c": member_count_start}],
        "member_start": member_count_start,
        "is_deleted": False,
        "created_at": _now()
    }
    await get_db().panels.insert_one(doc)
    return doc


async def _mongo_get_panel(token):
    from utils.db import get_db
    return await get_db().panels.find_one({"token": token, "is_deleted": False})


async def _mongo_get_panel_by_ref(ref_id):
    from utils.db import get_db
    return await get_db().panels.find_one({"ref_id": ref_id, "is_deleted": False})


async def _mongo_snapshot(token, member_count):
    from utils.db import get_db
    await get_db().panels.update_one(
        {"token": token},
        {"$push": {"member_snapshots": {"t": _now(), "c": member_count}}}
    )


async def _mongo_soft_delete(token):
    from utils.db import get_db
    await get_db().panels.update_one({"token": token}, {"$set": {"is_deleted": True}})


# ══════════════════════════════════════════════════════════════
# SQLITE
# ══════════════════════════════════════════════════════════════

async def _ensure_table():
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS panels (
                token TEXT PRIMARY KEY,
                owner_id INTEGER,
                panel_type TEXT,
                ref_id TEXT,
                channel_id TEXT,
                channel_username TEXT,
                channel_title TEXT,
                member_snapshots TEXT DEFAULT '[]',
                member_start INTEGER DEFAULT 0,
                is_deleted INTEGER DEFAULT 0,
                created_at TEXT
            )""")
        await conn.commit()


async def _sqlite_create_panel(owner_id, panel_type, ref_id, channel_id,
                                channel_username, channel_title, member_count_start):
    import aiosqlite
    from utils.db import get_sqlite_path
    await _ensure_table()
    token = _gen_token()
    snapshots = json.dumps([{"t": _now(), "c": member_count_start}])
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute(
            """INSERT INTO panels
               (token,owner_id,panel_type,ref_id,channel_id,channel_username,
                channel_title,member_snapshots,member_start,is_deleted,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,0,?)""",
            (token, owner_id, panel_type, ref_id, channel_id,
             channel_username, channel_title, snapshots, member_count_start, _now())
        )
        await conn.commit()
    return await _sqlite_get_panel(token)


async def _sqlite_get_panel(token):
    import aiosqlite
    from utils.db import get_sqlite_path
    await _ensure_table()
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM panels WHERE token=? AND is_deleted=0", (token,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["member_snapshots"] = json.loads(d["member_snapshots"])
    return d


async def _sqlite_get_panel_by_ref(ref_id):
    import aiosqlite
    from utils.db import get_sqlite_path
    await _ensure_table()
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM panels WHERE ref_id=? AND is_deleted=0", (ref_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["member_snapshots"] = json.loads(d["member_snapshots"])
    return d


async def _sqlite_snapshot(token, member_count):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        async with conn.execute(
            "SELECT member_snapshots FROM panels WHERE token=?", (token,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            snaps = json.loads(row[0])
            snaps.append({"t": _now(), "c": member_count})
            await conn.execute(
                "UPDATE panels SET member_snapshots=? WHERE token=?",
                (json.dumps(snaps), token)
            )
            await conn.commit()


async def _sqlite_soft_delete(token):
    import aiosqlite
    from utils.db import get_sqlite_path
    async with aiosqlite.connect(get_sqlite_path()) as conn:
        await conn.execute(
            "UPDATE panels SET is_deleted=1 WHERE token=?", (token,)
        )
        await conn.commit()


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

async def create_panel(owner_id, panel_type, ref_id, channel_id,
                        channel_username, channel_title, member_count_start=0):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_create_panel(owner_id, panel_type, ref_id, channel_id,
                                          channel_username, channel_title, member_count_start)
    return await _sqlite_create_panel(owner_id, panel_type, ref_id, channel_id,
                                       channel_username, channel_title, member_count_start)


async def get_panel(token):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_panel(token)
    return await _sqlite_get_panel(token)


async def get_panel_by_ref(ref_id):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_get_panel_by_ref(ref_id)
    return await _sqlite_get_panel_by_ref(ref_id)


async def add_snapshot(token, member_count):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_snapshot(token, member_count)
    return await _sqlite_snapshot(token, member_count)


async def soft_delete_panel(token):
    from utils.db import is_mongo
    if is_mongo():
        return await _mongo_soft_delete(token)
    return await _sqlite_soft_delete(token)
