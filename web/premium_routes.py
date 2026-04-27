
# ══════════════════════════════════════════════════════════════
# PREMIUM USER DASHBOARD  (/tg/premium/...)
# Path: /tg/premium/user/tg/security
# ══════════════════════════════════════════════════════════════
#
# Authentication flow:
#   1. Admin runs /addpreuser <tg_id>:<username>:<password> in bot
#   2. User visits /tg/premium/login  (Telegram Mini App)
#   3. On success → redirected to /tg/premium/user/tg/security
#   4. Dashboard fetches live data via /tg/premium/api/* endpoints
#
# Session cookies are separate from the admin panel sessions.
# ──────────────────────────────────────────────────────────────

import hashlib as _hashlib
import secrets as _secrets
import time as _time_prem

_prem_sessions: dict = {}          # token → expiry
_PREM_SESSION_TTL = 28800          # 8 hours


def _hash_prem_pw(pw: str) -> str:
    return _hashlib.sha256(pw.encode()).hexdigest()


def _get_prem_token(request: Request) -> str | None:
    return request.cookies.get("prem_session")


def _is_prem_auth(token: str | None) -> bool:
    if not token or token not in _prem_sessions:
        return False
    if _prem_sessions[token] < _time_prem.time():
        del _prem_sessions[token]
        return False
    return True


async def _check_prem_creds(username: str, password: str) -> bool:
    """Check username/password against premium_panel_users table."""
    try:
        from utils.db import get_db, is_mongo, get_sqlite_path
        hashed = _hash_prem_pw(password)
        if is_mongo():
            db = get_db()
            if db is None:
                return False
            return bool(await db.premium_panel_users.find_one(
                {"username": username, "password": hashed}
            ))
        import aiosqlite
        async with aiosqlite.connect(get_sqlite_path()) as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS premium_panel_users "
                "(id INTEGER PRIMARY KEY, tg_id INTEGER, username TEXT UNIQUE, password TEXT)"
            )
            await conn.commit()
            async with conn.execute(
                "SELECT id FROM premium_panel_users WHERE username=? AND password=?",
                (username, hashed)
            ) as cur:
                return await cur.fetchone() is not None
    except Exception as e:
        logger.error(f"_check_prem_creds error: {e}")
        return False


def _prem_login_html(error: str = "") -> str:
    """Load and render premium login page."""
    import os
    html_path = os.path.join(os.path.dirname(__file__), "premium_login.html")
    try:
        with open(html_path) as f:
            html = f.read()
    except FileNotFoundError:
        # Fallback inline login
        html = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Premium Login</title>
<style>*{box-sizing:border-box;margin:0;padding:0}
body{background:#07070e;color:#f1f0ff;font-family:sans-serif;min-height:100vh;
display:flex;align-items:center;justify-content:center;padding:24px}
.card{background:#0e0e1a;border:1px solid #1e1e32;border-radius:20px;padding:40px;
width:100%;max-width:380px}
h1{font-size:22px;margin-bottom:24px;text-align:center}
label{font-size:12px;color:#5a5880;display:block;margin-bottom:5px;text-transform:uppercase}
input{width:100%;background:#0d0d18;border:1px solid #1e1e32;border-radius:10px;
padding:12px 14px;color:#f1f0ff;font-size:14px;outline:none;margin-bottom:14px}
input:focus{border-color:#6c5ce7}
button{width:100%;background:#6c5ce7;border:none;border-radius:10px;
padding:13px;color:#fff;font-size:15px;font-weight:700;cursor:pointer}
.error{background:rgba(225,112,85,.1);border:1px solid rgba(225,112,85,.3);
color:#e17055;border-radius:8px;padding:10px;text-align:center;margin-bottom:14px;font-size:13px}
</style></head><body>
<div class="card">
  <h1>👑 Premium Login</h1>
  __ERROR_BLOCK__
  <form method="POST">
    <label>Username</label><input type="text" name="username" required>
    <label>Password</label><input type="password" name="password" required>
    <button type="submit">Sign In →</button>
  </form>
</div></body></html>"""

    err_html = f'<div class="error">{error}</div>' if error else ""
    return html.replace("__ERROR_BLOCK__", err_html)


def _prem_403_html() -> str:
    return """<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Access Denied</title>
<style>*{box-sizing:border-box;margin:0;padding:0}
body{background:#07070e;color:#f1f0ff;font-family:sans-serif;min-height:100vh;
display:flex;align-items:center;justify-content:center;text-align:center;padding:24px}
.icon{font-size:64px;margin-bottom:16px}h1{font-size:24px;margin-bottom:10px}
p{color:#5a5880;font-size:14px;line-height:1.6;max-width:320px}
a{color:#6c5ce7;text-decoration:none;display:inline-block;margin-top:20px;
font-size:13px;border:1px solid #6c5ce7;border-radius:8px;padding:8px 20px}
</style></head><body><div>
<div class="icon">🔒</div>
<h1>Premium Access Only</h1>
<p>This dashboard is available to premium users only.<br>
Contact your admin to get access.</p>
<a href="/tg/premium/login">← Go to Login</a>
</div></body></html>"""


# ── Login ──────────────────────────────────────────────────────
@app.get("/tg/premium/login", response_class=HTMLResponse)
async def prem_login_get():
    return HTMLResponse(_prem_login_html())


@app.post("/tg/premium/login")
async def prem_login_post(request: Request):
    _rate_guard(request)
    try:
        form = await request.form()
        username = form.get("username", "").strip()
        password = form.get("password", "")
        if await _check_prem_creds(username, password):
            tok = _secrets.token_hex(32)
            _prem_sessions[tok] = _time_prem.time() + _PREM_SESSION_TTL
            r = RedirectResponse(url="/tg/premium/user/tg/security", status_code=302)
            r.set_cookie("prem_session", tok, httponly=True, max_age=_PREM_SESSION_TTL, samesite="lax")
            return r
        return HTMLResponse(_prem_login_html("❌ Invalid username or password"))
    except Exception as e:
        logger.error(f"prem_login_post error: {e}")
        return HTMLResponse(_prem_login_html("❌ Server error, please try again"))


@app.get("/tg/premium/logout")
async def prem_logout(request: Request):
    tok = _get_prem_token(request)
    if tok and tok in _prem_sessions:
        del _prem_sessions[tok]
    r = RedirectResponse(url="/tg/premium/login", status_code=302)
    r.delete_cookie("prem_session")
    return r


# ── Main dashboard (the Mini App entry point) ──────────────────
@app.get("/tg/premium/user/tg/security", response_class=HTMLResponse)
async def prem_dashboard(request: Request):
    _rate_guard(request)
    if not _is_prem_auth(_get_prem_token(request)):
        return RedirectResponse(url="/tg/premium/login", status_code=302)
    import os
    html_path = os.path.join(os.path.dirname(__file__), "premium_dashboard.html")
    try:
        with open(html_path) as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Dashboard file not found</h1>", status_code=500)


# ── Premium API endpoints (re-expose existing data under /tg/premium/api/) ──
# These proxy the existing data builders so the dashboard JS can call them
# without needing admin-panel session cookies.

def _prem_guard(request: Request):
    """Raise 401 if not a valid premium session."""
    if not _is_prem_auth(_get_prem_token(request)):
        raise HTTPException(status_code=401, detail="Not authenticated")


@app.get("/tg/premium/api/stats")
async def prem_api_stats(request: Request):
    _rate_guard(request)
    _prem_guard(request)
    return JSONResponse(await _build_stats())


@app.get("/tg/premium/api/clones")
async def prem_api_clones(request: Request):
    _rate_guard(request)
    _prem_guard(request)
    return JSONResponse(await _build_clones())


@app.get("/tg/premium/api/giveaways")
async def prem_api_giveaways(request: Request):
    _rate_guard(request)
    _prem_guard(request)
    return JSONResponse(await _build_giveaways())


@app.get("/tg/premium/api/users")
async def prem_api_users(request: Request, page: int = 1, search: str = ""):
    _rate_guard(request)
    _prem_guard(request)
    return JSONResponse(await _build_users(page=page, search=search))


@app.get("/tg/premium/api/live_users")
async def prem_api_live_users(request: Request):
    _rate_guard(request)
    _prem_guard(request)
    from utils.db import get_db, is_mongo, get_sqlite_path
    try:
        if is_mongo():
            count = await get_db().main_bot_users.count_documents({})
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                async with conn.execute("SELECT COUNT(*) FROM main_bot_users") as cur:
                    count = (await cur.fetchone())[0]
        return JSONResponse({"count": count})
    except Exception as e:
        return JSONResponse({"count": 0, "error": str(e)})


@app.get("/tg/premium/api/clone_users/{token}")
async def prem_api_clone_users(token: str, request: Request):
    _rate_guard(request)
    _prem_guard(request)
    from utils.db import get_db, is_mongo, get_sqlite_path
    users = []
    try:
        if is_mongo():
            db = get_db()
            docs = await db.referrals.find({"clone_token": token}).sort("refer_count", -1).to_list(None)
            users = [{"user_id": d.get("user_id"), "user_name": d.get("user_name") or "—",
                      "refer_count": d.get("refer_count", 0), "joined_at": str(d.get("joined_at", ""))[:10]}
                     for d in docs]
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT user_id, user_name, refer_count, joined_at FROM referrals "
                    "WHERE clone_token=? ORDER BY refer_count DESC", (token,)
                ) as cur:
                    rows = await cur.fetchall()
            users = [{"user_id": r["user_id"], "user_name": r["user_name"] or "—",
                      "refer_count": r["refer_count"] or 0, "joined_at": str(r["joined_at"] or "")[:10]}
                     for r in rows]
    except Exception as e:
        logger.error(f"prem clone_users error: {e}")
        raise HTTPException(500, detail=str(e))
    return JSONResponse({"token": token, "users": users, "total": len(users)})


@app.get("/tg/premium/api/panels")
async def prem_api_panels(request: Request):
    _rate_guard(request)
    _prem_guard(request)
    return JSONResponse(await _build_panels())


# ── Add premium panel user (called from Telegram bot admin command) ──
async def add_premium_panel_user(tg_id: int, username: str, password: str) -> bool:
    """
    Store a premium dashboard user in premium_panel_users table.
    Called by the /addpreuser bot command handler in handlers/admin.py
    """
    try:
        from utils.db import get_db, is_mongo, get_sqlite_path
        hashed = _hash_prem_pw(password)
        if is_mongo():
            db = get_db()
            await db.premium_panel_users.update_one(
                {"username": username},
                {"$set": {"tg_id": tg_id, "username": username, "password": hashed}},
                upsert=True,
            )
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                await conn.execute(
                    "CREATE TABLE IF NOT EXISTS premium_panel_users "
                    "(id INTEGER PRIMARY KEY, tg_id INTEGER, username TEXT UNIQUE, password TEXT)"
                )
                await conn.execute(
                    "INSERT OR REPLACE INTO premium_panel_users (tg_id, username, password) VALUES (?,?,?)",
                    (tg_id, username, hashed)
                )
                await conn.commit()
        logger.info(f"✅ Premium panel user added: @{username} (tg_id={tg_id})")
        return True
    except Exception as e:
        logger.error(f"add_premium_panel_user error: {e}")
        return False


async def remove_premium_panel_user(username: str) -> bool:
    """Remove a premium dashboard user. Called by /removepreuser bot command."""
    try:
        from utils.db import get_db, is_mongo, get_sqlite_path
        if is_mongo():
            result = await get_db().premium_panel_users.delete_one({"username": username})
            return result.deleted_count > 0
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                cur = await conn.execute(
                    "DELETE FROM premium_panel_users WHERE username=?", (username,)
                )
                await conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"remove_premium_panel_user error: {e}")
        return False
