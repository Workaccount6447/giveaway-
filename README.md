# 👑 RoyalityBots — Telegram Giveaway & Referral Bot

A full-featured Telegram bot platform with live giveaway polls, referral tracking, analytics panels, and a beautiful admin dashboard.

---

## 🚀 Deploy on Render (Recommended)

### Step 1 — MongoDB Atlas (free)
1. Go to [mongodb.com/atlas](https://www.mongodb.com/atlas) → Create free account
2. Create a free M0 cluster
3. Database Access → Add user → copy username & password
4. Network Access → Allow access from anywhere (`0.0.0.0/0`)
5. Connect → Drivers → copy connection string
   - Looks like: `mongodb+srv://user:pass@cluster.mongodb.net/giveawaybot`

### Step 2 — Create your Telegram bot
1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the **bot token**
3. Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot)

### Step 3 — Deploy on Render
1. Push this repo to **GitHub**
2. Go to [render.com](https://render.com) → New → **Web Service**
3. Connect your GitHub repo
4. Set these:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
5. Add environment variables (see below)
6. Click **Deploy**

### Step 4 — Environment Variables on Render

| Variable | Value | Notes |
|---|---|---|
| `BOT_TOKEN` | `7123456:AAF...` | From BotFather |
| `MONGO` | `true` | Use MongoDB |
| `MONGO_URI` | `mongodb+srv://...` | From Atlas |
| `SUPERADMIN_IDS` | `[123456789]` | Your Telegram ID |
| `WEB_DOMAIN` | `your-app.onrender.com` | Your Render URL |

> ⚠️ Do NOT set `WEB_PORT` on Render — it's set automatically via the `PORT` env var.

### Step 5 — First setup
After deploy, message your bot:
```
/addadmin yourusername:yourpassword
```
Then open: `https://your-app.onrender.com/adminpanel/royalisbest/a?b3c`

---

## 🏃 Run Locally

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your values (set MONGO=false for SQLite)

# 3. Run
python main.py
```

Local admin panel: `http://localhost:8080/adminpanel/royalisbest/a?b3c`

---

## 📁 Project Structure

```
├── main.py                      # Entry point
├── config/settings.py           # All env config
├── handlers/
│   ├── start.py                 # /start, /help, main menu
│   ├── giveaway.py              # Poll creation, voting, schedule, reopen
│   ├── clone_bot.py             # Clone bot setup & management
│   ├── admin.py                 # Superadmin commands + /addadmin
│   └── referral.py              # /mygiveaways
├── models/
│   ├── giveaway.py              # Giveaway DB (Mongo + SQLite)
│   ├── referral.py              # Clone bots + referral DB
│   └── panel.py                 # Analytics panel DB
├── utils/
│   ├── db.py                    # DB switcher (MONGO=true/false)
│   ├── clone_manager.py         # Runs all clone bots as tasks
│   ├── poll_renderer.py         # █░ bar chart renderer
│   ├── snapshot_scheduler.py    # Channel member snapshots (30 min)
│   ├── keep_alive.py            # Render anti-sleep pinger
│   └── languages.py             # EN/HI strings
└── web/
    ├── app.py                   # FastAPI server
    ├── broadcaster.py           # Global broadcast helper
    ├── admin_dashboard.html     # Admin panel UI
    └── user_panel.html          # User analytics panel UI
```

---

## 🗳 Giveaway Poll Feature

### Setup:
1. Add bot as **admin** in your Telegram channel
2. Send `/creategiveaway` to the bot in DM
3. Follow the 5-step wizard:
   - Channel username
   - Title
   - Prizes (one per line)
   - Participants/options (one per line)
   - End time (optional: `2h`, `30m`, `1d`)

### After posting:
- Poll appears in channel with live vote bars `█░░░░░░░`
- Users must join the channel to vote
- Creator gets a **analytics panel link** automatically
- On poll close → creator gets full results report in DM

### Commands:
| Command | Description |
|---|---|
| `/creategiveaway` | Start giveaway wizard |
| `/mygiveaways` | List your giveaways |
| `/closegiveaway <ID>` | Close a poll manually |
| `/reopenpoll <ID>` | Reopen a closed poll |
| `/schedulepost <ID> 2h` | Post an existing giveaway after delay |

---

## 🤖 Clone Refer Bot Feature

### How it works:
1. User creates a bot via @BotFather
2. Sends `/clonebot` to main bot, pastes their token
3. Goes through 4-step setup:
   - Bot token
   - Channel join gate (optional)
   - Welcome message (or default)
   - Custom referral caption (or default)
4. Bot launches instantly with referral tracking

### Clone bot — user commands:
| Command | Description |
|---|---|
| `/start` | Welcome + language picker + channel join check |
| `/refer` | Get personal referral link |
| `/mystats` | Personal referral count |
| `/leaderboard` | Top 10 referrers |
| `/myreferrals` | See who you referred |

### Clone bot — owner commands:
| Command | Description |
|---|---|
| `/all` | Full participant leaderboard |
| `/broadcast <msg>` | Message all users |
| `/schedulebroadcast 2h <msg>` | Delayed broadcast |
| `/exportusers` | Download users as CSV |
| `/botstats` | Daily joins chart + top referrer |
| `/resetreferral <user_id>` | Reset a user's count |
| `/banuser <user_id>` | Ban user from bot |
| `/setwelcomeimage` | Reply to photo to set welcome image |
| `/clearwelcomeimage` | Remove welcome image |
| `/togglecommands` | Enable/disable user commands |

---

## 📊 Analytics Panels

Every giveaway and clone bot gets a **unique public link** automatically:
```
https://your-app.onrender.com/panel/<random_token>
```

**Giveaway panel shows:**
- Channel name, members before/during/gained
- Prize cards
- Vote distribution bar chart
- Full ranked results with progress bars
- Sort by votes or A–Z

**Refer bot panel shows:**
- Channel growth chart (snapshots every 30 min)
- Total users, active referrers, top referrer
- Referrer leaderboard with progress bars

---

## 🌐 Admin Panel

URL: `https://your-app.onrender.com/adminpanel/royalisbest/a?b3c`

**Create login via bot:**
```
/addadmin username:password
```

**Features:**
- Live stats: clone bots, users, polls, votes, uptime
- Daily joins chart + bot usage chart
- Clone bots table with Ban button
- Giveaways table
- User panels list with view/delete
- Global broadcast to all users
- User ban

---

## ⚙️ All Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | required | Main bot token from BotFather |
| `MONGO` | `true` | `true`=MongoDB, `false`=SQLite |
| `MONGO_URI` | localhost | MongoDB connection string |
| `SUPERADMIN_IDS` | `[]` | Your Telegram user ID(s) |
| `WEB_DOMAIN` | `your-app.onrender.com` | Your public domain |
| `WEB_PORT` | auto | Port (auto on Render via `PORT`) |

---

## 🔧 Render Notes

- **Free tier** — bot stays alive via built-in keep-alive pinger (pings `/health` every 14 min)
- **Paid tier** — disable keep-alive or ignore it, no sleep on paid plans
- **MongoDB** — always use MongoDB Atlas on Render (SQLite doesn't persist on free Render)
- **Logs** — check Render dashboard → your service → Logs tab
- **Redeploy** — push to GitHub, Render auto-deploys
