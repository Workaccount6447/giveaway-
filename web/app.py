import os
import asyncio
import time
import hashlib
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

app = FastAPI(docs_url=None, redoc_url=None)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

_sessions: dict = {}
_start_time = time.time()
PANEL_SECRET = "royalisbest"
PANEL_PARAM = "b3c"


def _hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def _get_token(request):
    return request.cookies.get("panel_session")


def _is_auth(token):
    if not token or token not in _sessions:
        return False
    return time.time() - _sessions[token] < 86400  # 24h


async def start_cmd(message: Message):
    await message.answer("Bot is running!")


async def echo(message: Message):
    await message.answer(message.text)


async def _check_creds(username, password):
    from utils.db import get_db, is_mongo, get_sqlite_path
    hashed = _hash_pw(password)
    if is_mongo():
        db = get_db()
        user = await db.panel_users.find_one({"username": username})
        return user and user.get("password") == hashed
    else:
        import aiosqlite
        async with aiosqlite.connect(get_sqlite_path()) as conn:
            async with conn.execute(
                "SELECT password FROM panel_users WHERE username=?", (username,)
            ) as cur:
                row = await cur.fetchone()
        return row and row[0] == hashed


def _login_html(error=""):
    err_html = f'<div style="color:red;margin-bottom:10px;">{error}</div>' if error else ""
    return f"""<!DOCTYPE html>
<html>
<head><title>RoyalityBots — Admin Login</title>
<style>
  body {{ font-family: Arial; background: #0a0a0f; color: #f1f0ff; margin: 0; padding: 20px; }}
  .container {{ max-width: 400px; margin: 80px auto; background: #1a1a2e; padding: 30px; border-radius: 12px; border: 1px solid #2a2a45; }}
  h1 {{ text-align: center; margin-bottom: 30px; }}
  input {{ width: 100%; padding: 12px; margin: 10px 0; background: #0e0e1a; border: 1px solid #2a2a45; color: #f1f0ff; border-radius: 6px; box-sizing: border-box; }}
  button {{ width: 100%; padding: 12px; margin-top: 20px; background: #6d28d9; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }}
  button:hover {{ background: #8b5cf6; }}
</style>
</head>
<body>
<div class="container">
  <h1>🔐 Admin Login</h1>
  {err_html}
  <form method="post" action="/login">
    <input type="text" name="username" placeholder="Username" required>
    <input type="password" name="password" placeholder="Password" required>
    <button type="submit">Login</button>
  </form>
</div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return _login_html()


@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    return _login_html(error)


@app.post("/login")
async def login_post(request: Request):
    try:
        form = await request.form()
        username = form.get("username", "").strip()
        password = form.get("password", "").strip()

        if not username or not password:
            return HTMLResponse(_login_html("Username and password required"), status_code=400)

        if await _check_creds(username, password):
            token = hashlib.sha256(f"{username}{time.time()}".encode()).hexdigest()
            _sessions[token] = time.time()
            response = HTMLResponse(
                """<html><body><script>
                document.location='/admin';
                </script></body></html>"""
            )
            response.set_cookie("panel_session", token, max_age=86400, httponly=True)
            return response
        else:
            return HTMLResponse(_login_html("Invalid credentials"), status_code=401)
    except Exception as e:
        return HTMLResponse(_login_html(f"Error: {str(e)}"), status_code=500)


@app.get("/logout")
async def logout(request: Request):
    token = _get_token(request)
    if token and token in _sessions:
        del _sessions[token]
    response = HTMLResponse(
        """<html><body><script>
        document.location='/login';
        </script></body></html>"""
    )
    response.delete_cookie("panel_session")
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        return HTMLResponse(_login_html("Session expired"), status_code=401)
    
    try:
        html = _admin_html()
        return html
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)


@app.get("/api/stats")
async def api_stats(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        stats = await _build_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clones")
async def api_clones(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        clones = await _build_clones()
        return clones
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/giveaways")
async def api_giveaways(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        giveaways = await _build_giveaways()
        return giveaways
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/panels")
async def api_panels(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        panels = await _build_panels()
        return panels
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ban-clone")
async def api_ban_clone(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        data = await request.json()
        clone_token = data.get("token")
        if not clone_token:
            raise HTTPException(status_code=400, detail="Token required")
        
        from utils.clone_manager import get_clone_manager
        from models.referral import ban_clone_bot
        await get_clone_manager().stop_clone(clone_token)
        await ban_clone_bot(clone_token)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/broadcast")
async def api_broadcast(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        data = await request.json()
        message = data.get("message")
        if not message:
            raise HTTPException(status_code=400, detail="Message required")
        
        from web.broadcaster import do_global_broadcast
        await do_global_broadcast(message)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/delete-panel")
async def api_delete_panel(request: Request):
    token = _get_token(request)
    if not _is_auth(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        data = await request.json()
        panel_token = data.get("token")
        if not panel_token:
            raise HTTPException(status_code=400, detail="Token required")
        
        from models.panel import soft_delete_panel
        await soft_delete_panel(panel_token)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/panel/{token}", response_class=HTMLResponse)
async def user_panel(token: str):
    try:
        from models.panel import get_panel
        panel = await get_panel(token)
        if not panel:
            return _not_found_html()
        
        data = await _build_panel_data(panel)
        html = _user_panel_html(panel, data)
        return html
    except Exception as e:
        return _not_found_html()


@app.get("/api/panel/{token}")
async def user_panel_data(token: str):
    try:
        from models.panel import get_panel
        panel = await get_panel(token)
        if not panel:
            raise HTTPException(status_code=404, detail="Panel not found")
        
        data = await _build_panel_data(panel)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/panel/{token}/delete")
async def user_panel_delete(token: str, request: Request):
    try:
        from models.panel import soft_delete_panel
        await soft_delete_panel(token)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _build_stats():
    from utils.db import is_mongo, get_db, get_sqlite_path
    
    try:
        if is_mongo():
            db = get_db()
            total_clones = await db.clone_bots.count_documents({"is_active": True})
            total_users = await db.referrals.count_documents({})
            total_giveaways = await db.giveaways.count_documents({})
            active_giveaways = await db.giveaways.count_documents({"is_active": True})
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                async def cnt(q, p=()):
                    async with conn.execute(q, p) as c:
                        return (await c.fetchone())[0] or 0
                
                total_clones = await cnt("SELECT COUNT(*) FROM clone_bots WHERE is_active=1")
                total_users = await cnt("SELECT COUNT(*) FROM referrals")
                total_giveaways = await cnt("SELECT COUNT(*) FROM giveaways")
                active_giveaways = await cnt("SELECT COUNT(*) FROM giveaways WHERE is_active=1")
        
        return {
            "total_clones": total_clones,
            "total_users": total_users,
            "total_giveaways": total_giveaways,
            "active_giveaways": active_giveaways,
            "uptime": int(time.time() - _start_time)
        }
    except Exception as e:
        return {"error": str(e)}


async def _build_clones():
    from models.referral import get_all_clone_bots
    
    try:
        clones = await get_all_clone_bots()
        return [
            {
                "token": c.get("token", ""),
                "username": c.get("bot_username", "unknown"),
                "owner_id": c.get("owner_id", 0),
                "is_active": c.get("is_active", True),
                "is_banned": c.get("is_banned", False)
            }
            for c in clones
        ]
    except Exception as e:
        return {"error": str(e)}


async def _build_giveaways():
    from utils.db import is_mongo, get_db, get_sqlite_path
    
    try:
        if is_mongo():
            db = get_db()
            giveaways = await db.giveaways.find({}).sort("created_at", -1).to_list(length=50)
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM giveaways ORDER BY created_at DESC LIMIT 50"
                ) as cur:
                    rows = await cur.fetchall()
            giveaways = [dict(r) for r in rows]
        
        return [
            {
                "id": g.get("giveaway_id", ""),
                "title": g.get("title", ""),
                "creator_id": g.get("creator_id", 0),
                "is_active": g.get("is_active", False),
                "total_votes": g.get("total_votes", 0)
            }
            for g in giveaways
        ]
    except Exception as e:
        return {"error": str(e)}


async def _build_panels():
    from utils.db import is_mongo, get_db, get_sqlite_path
    
    try:
        if is_mongo():
            db = get_db()
            panels = await db.panels.find({"is_deleted": False}).to_list(length=50)
        else:
            import aiosqlite
            async with aiosqlite.connect(get_sqlite_path()) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM panels WHERE is_deleted=0 LIMIT 50"
                ) as cur:
                    rows = await cur.fetchall()
            panels = [dict(r) for r in rows]
        
        return [
            {
                "token": p.get("token", ""),
                "owner_id": p.get("owner_id", 0),
                "type": p.get("panel_type", ""),
                "ref_id": p.get("ref_id", ""),
                "title": p.get("channel_title", "")
            }
            for p in panels
        ]
    except Exception as e:
        return {"error": str(e)}


async def _build_panel_data(panel: dict) -> dict:
    from utils.db import is_mongo, get_db, get_sqlite_path
    
    try:
        token = panel.get("token", "")
        ref_id = panel.get("ref_id", "")
        panel_type = panel.get("panel_type", "")
        
        if panel_type == "refer":
            if is_mongo():
                db = get_db()
                total_refs = await db.referrals.count_documents({"clone_token": ref_id})
                top = await db.referrals.find_one(
                    {"clone_token": ref_id},
                    sort=[("refer_count", -1)]
                )
            else:
                import aiosqlite
                async with aiosqlite.connect(get_sqlite_path()) as conn:
                    async with conn.execute(
                        "SELECT COUNT(*) FROM referrals WHERE clone_token=?", (ref_id,)
                    ) as cur:
                        total_refs = (await cur.fetchone())[0] or 0
                    async with conn.execute(
                        "SELECT * FROM referrals WHERE clone_token=? ORDER BY refer_count DESC LIMIT 1",
                        (ref_id,)
                    ) as cur:
                        top = await cur.fetchone()
            
            return {
                "type": "refer",
                "total_users": total_refs,
                "top_referrer_count": top.get("refer_count", 0) if isinstance(top, dict) else (top[5] if top else 0)
            }
        else:
            if is_mongo():
                db = get_db()
                giveaway = await db.giveaways.find_one({"giveaway_id": ref_id})
            else:
                import aiosqlite
                async with aiosqlite.connect(get_sqlite_path()) as conn:
                    conn.row_factory = aiosqlite.Row
                    async with conn.execute(
                        "SELECT * FROM giveaways WHERE giveaway_id=?", (ref_id,)
                    ) as cur:
                        row = await cur.fetchone()
                giveaway = dict(row) if row else None
            
            return {
                "type": "giveaway",
                "total_votes": giveaway.get("total_votes", 0) if giveaway else 0,
                "is_active": giveaway.get("is_active", False) if giveaway else False
            }
    except Exception as e:
        return {"error": str(e)}


@app.get("/health")
async def health():
    return {"status": "ok", "uptime": int(time.time() - _start_time)}


def _admin_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RoyalityBots — Admin</title>
<style>
body { font-family: Arial, sans-serif; background: #0a0a0f; color: #f1f0ff; margin: 0; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { text-align: center; margin-bottom: 30px; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }
.stat { background: #1a1a2e; padding: 20px; border-radius: 8px; border: 1px solid #2a2a45; text-align: center; }
.stat-val { font-size: 32px; font-weight: bold; color: #8b5cf6; }
.stat-label { font-size: 12px; color: #6b7280; margin-top: 5px; }
.panel { background: #1a1a2e; padding: 20px; border-radius: 8px; border: 1px solid #2a2a45; margin-bottom: 20px; }
.panel h2 { margin-top: 0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid #2a2a45; }
th { font-weight: bold; background: #0a0a0f; }
a { color: #8b5cf6; text-decoration: none; }
a:hover { text-decoration: underline; }
.btn { padding: 10px 20px; background: #6d28d9; color: white; border: none; border-radius: 4px; cursor: pointer; }
.btn:hover { background: #8b5cf6; }
.logout { float: right; }
</style>
</head>
<body>
<div class="container">
  <h1>🛠 Admin Dashboard</h1>
  <a href="/logout" class="btn logout">Logout</a>
  <div class="stats" id="stats-container">
    <div class="stat"><div class="stat-val">-</div><div class="stat-label">Active Clones</div></div>
    <div class="stat"><div class="stat-val">-</div><div class="stat-label">Total Users</div></div>
    <div class="stat"><div class="stat-val">-</div><div class="stat-label">Total Giveaways</div></div>
    <div class="stat"><div class="stat-val">-</div><div class="stat-label">Active Giveaways</div></div>
  </div>
  <div class="panel">
    <h2>📊 System Status</h2>
    <p>Server is running. Load data with JavaScript.</p>
  </div>
</div>
<script>
fetch('/api/stats').then(r => r.json()).then(data => {
  if (!data.error) {
    document.querySelectorAll('.stat-val')[0].textContent = data.total_clones || 0;
    document.querySelectorAll('.stat-val')[1].textContent = data.total_users || 0;
    document.querySelectorAll('.stat-val')[2].textContent = data.total_giveaways || 0;
    document.querySelectorAll('.stat-val')[3].textContent = data.active_giveaways || 0;
  }
}).catch(e => console.error('Stats error:', e));
</script>
</body>
</html>"""


def _user_panel_html(panel, data):
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Analytics — RoyalityBots</title>
<style>
body { font-family: Arial, sans-serif; background: #0a0a0f; color: #f1f0ff; margin: 0; padding: 20px; }
.container { max-width: 800px; margin: 0 auto; }
h1 { text-align: center; margin-bottom: 30px; }
.panel { background: #1a1a2e; padding: 20px; border-radius: 8px; border: 1px solid #2a2a45; }
.stat { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }
.stat-item { background: #0a0a0f; padding: 15px; border-radius: 6px; }
.stat-val { font-size: 24px; font-weight: bold; color: #8b5cf6; }
.stat-label { font-size: 12px; color: #6b7280; margin-top: 5px; }
</style>
</head>
<body>
<div class="container">
  <h1>📊 Panel Analytics</h1>
  <div class="panel">
    <h2 id="panel-title">Loading...</h2>
    <div class="stat" id="stats-container">
      <div class="stat-item"><div class="stat-val">-</div><div class="stat-label">Metric 1</div></div>
      <div class="stat-item"><div class="stat-val">-</div><div class="stat-label">Metric 2</div></div>
    </div>
  </div>
</div>
<script>
const token = window.location.pathname.split('/').pop();
fetch('/api/panel/' + token).then(r => r.json()).then(data => {
  document.getElementById('panel-title').textContent = data.type === 'refer' ? '🔗 Referral Panel' : '🗳 Giveaway Panel';
}).catch(e => console.error('Error:', e));
</script>
</body>
</html>"""


def _not_found_html():
    return """<!DOCTYPE html>
<html>
<head><title>Panel Not Found</title>
<style>
body { font-family: Arial; background: #0a0a0f; color: #f1f0ff; margin: 0; padding: 20px; text-align: center; }
.container { max-width: 500px; margin: 100px auto; }
h1 { color: #f43f5e; }
</style>
</head>
<body>
<div class="container">
  <h1>❌ Panel Not Found</h1>
  <p>This panel link is invalid or has been deleted.</p>
</div>
</body>
</html>"""


def run_web(host="0.0.0.0", port=8080):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_web()
