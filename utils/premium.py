"""
utils/premium.py

Premium user management.
- Superadmin grants premium via /addpremium <user_id> <days>
- Superadmin revokes via /removepremium <user_id>
- Premium users have no "Made via @RoyalityBots" stamp on polls/messages
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def add_premium(user_id: int, days: int, granted_by: int) -> datetime:
    """Grant premium to user for N days. Returns expiry datetime."""
    from utils.db import get_db, is_mongo, get_sqlite_path
    expires_at = _now() + timedelta(days=days)
    granted_at = _now()

    if is_mongo():
        await get_db().premium_users.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id":    user_id,
                "granted_by": granted_by,
                "expires_at": expires_at.isoformat(),
                "granted_at": granted_at.isoformat(),
            }},
            upsert=True,
        )
    else:
        import aiosqlite
        async with aiosqlite.connect(get_sqlite_path()) as conn:
            await conn.execute(
                """INSERT INTO premium_users (user_id, granted_by, expires_at, granted_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     granted_by=excluded.granted_by,
                     expires_at=excluded.expires_at,
                     granted_at=excluded.granted_at""",
                (user_id, granted_by, expires_at.isoformat(), granted_at.isoformat())
            )
            await conn.commit()

    logger.info(f"✅ Premium granted: user={user_id} days={days} expires={expires_at.date()}")
    return expires_at


async def remove_premium(user_id: int) -> bool:
    """Revoke premium. Returns True if user had premium."""
    from utils.db import get_db, is_mongo, get_sqlite_path

    if is_mongo():
        result = await get_db().premium_users.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    else:
        import aiosqlite
        async with aiosqlite.connect(get_sqlite_path()) as conn:
            cur = await conn.execute("DELETE FROM premium_users WHERE user_id=?", (user_id,))
            await conn.commit()
            return cur.rowcount > 0


async def is_premium(user_id: int) -> bool:
    """Return True if user has active (non-expired) premium."""
    from utils.db import get_db, is_mongo, get_sqlite_path

    try:
        if is_mongo():
            doc = await get_db().premium_users.find_one({"user_id": user_id})
            if not doc:
                return False
            expires_at = datetime.fromisoformat(doc["expires_at"])
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                async with conn.execute(
                    "SELECT expires_at FROM premium_users WHERE user_id=?", (user_id,)
                ) as cur:
                    row = await cur.fetchone()
            if not row:
                return False
            expires_at = datetime.fromisoformat(row[0])

        # Make timezone-aware if naive
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return _now() < expires_at

    except Exception as e:
        logger.warning(f"is_premium({user_id}) error: {e}")
        return False


async def get_premium_info(user_id: int) -> dict | None:
    """Return premium doc or None."""
    from utils.db import get_db, is_mongo, get_sqlite_path

    try:
        if is_mongo():
            return await get_db().premium_users.find_one({"user_id": user_id})
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM premium_users WHERE user_id=?", (user_id,)
                ) as cur:
                    row = await cur.fetchone()
            return dict(row) if row else None
    except Exception:
        return None
