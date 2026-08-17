import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5932054746
DB_PATH = "earning_real.db"

DEFAULT_AD_REWARD = 0.0001
DEFAULT_REF_REWARD = 0.001
DEFAULT_MIN_WITHDRAW = 0.50

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables.")

# ---------- Database ----------
def db():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT '',
        balance REAL DEFAULT 0,
        referral_count INTEGER DEFAULT 0,
        referred_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        reward REAL NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        wallet TEXT NOT NULL,
        amount REAL NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        paid_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        kind TEXT NOT NULL,
        note TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.commit()
    return c

def setting(key, default):
    c = db()
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not r:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?)", (key, str(default)))
        c.commit()
        v = str(default)
    else:
        v = r["value"]
    c.close()
    return v

def set_setting(key, value):
    c = db()
    c.execute("""INSERT INTO settings(key,value) VALUES(?,?)
                 ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
              (key, str(value)))
    c.commit()
    c.close()

def ad_reward(): return float(setting("ad_reward", DEFAULT_AD_REWARD))
def ref_reward(): return float(setting("ref_reward", DEFAULT_REF_REWARD))
def min_withdraw(): return float(setting("min_withdraw", DEFAULT_MIN_WITHDRAW))

# ---------- UI ----------
def home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Watch Ads & Earn", callback_data="ads")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("👥 Referral", callback_data="ref")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
         InlineKeyboardButton("📜 History", callback_data="history")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

def back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="a_stats"),
         InlineKeyboardButton("👥 Users", callback_data="a_users")],
        [InlineKeyboardButton("🎬 Ad Settings", callback_data="a_ads"),
         InlineKeyboardButton("💸 Withdrawals", callback_data="a_withdrawals")],
        [InlineKeyboardButton("📖 All Commands", callback_data="a_commands")],
        [InlineKeyboardButton("🏠 Home", callback_data="home")]
    ])

# ---------- Users ----------
async def register(user, ref=None):
    c = db()
    r = c.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not r:
        valid = None
        if ref and ref != user.id:
            rr = c.execute("SELECT user_id FROM users WHERE user_id=?", (ref,)).fetchone()
            if rr:
                valid = ref
        c.execute("INSERT INTO users(user_id,username,referred_by) VALUES(?,?,?)",
                  (user.id, user.username or "", valid))
        if valid:
            reward = ref_reward()
            c.execute("UPDATE users SET balance=balance+?, referral_count=referral_count+1 WHERE user_id=?",
                      (reward, valid))
            c.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(?,?,?,?)",
                      (valid, reward, "referral", "Qualifying referral"))
    else:
        c.execute("UPDATE users SET username=? WHERE user_id=?", (user.username or "", user.id))
    c.commit()
    c.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ref = None
    if context.args and context.args[0].startswith("ref_"):
        try: ref = int(context.args[0][4:])
        except ValueError: pass
    await register(update.effective_user, ref)
    await update.message.reply_text(
        "🌟 *BNB TOKEN MINING*\n\n"
        "🎬 Watch ads & earn\n"
        "👥 Refer friends\n"
        "💰 Check balance\n"
        "💸 Withdraw from $0.50\n\n"
        "Select an option 👇",
        parse_mode="Markdown", reply_markup=home()
    )

# ---------- User pages ----------
async def page_ads(q):
    c = db()
    ad = c.execute("SELECT * FROM ads WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    c.close()
    if not ad:
        await q.edit_message_text(
            "🎬 *Ad Center*\n\nNo Monetag ad link has been added yet.",
            parse_mode="Markdown", reply_markup=back())
        return
    await q.edit_message_text(
        "🎬 *WATCH ADS & EARN*\n\n"
        f"💵 Reward shown: *${float(ad['reward']):.4f}*\n\n"
        "Tap below to open the ad.\n\n"
        "⚠️ A normal SmartLink click is not automatically verified as a completed rewarded ad.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ OPEN AD", url=ad["url"])],
            [InlineKeyboardButton("ℹ️ Reward Info", callback_data="ad_info")],
            [InlineKeyboardButton("🔙 Back", callback_data="home")]
        ]))

async def page_balance(q):
    c = db()
    r = c.execute("SELECT balance FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()
    c.close()
    b = float(r["balance"]) if r else 0
    await q.edit_message_text(
        "💰 *MY BALANCE*\n\n"
        f"💵 Balance: *${b:.4f}*\n"
        f"🔒 Minimum withdrawal: *${min_withdraw():.2f}*\n"
        "🟡 Network: *BNB Smart Chain (BEP20)*",
        parse_mode="Markdown", reply_markup=back())

async def page_ref(q):
    me = await q.get_bot().get_me()
    link = f"https://t.me/{me.username}?start=ref_{q.from_user.id}"
    c = db()
    r = c.execute("SELECT referral_count FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()
    c.close()
    count = int(r["referral_count"]) if r else 0
    await q.edit_message_text(
        "👥 *REFER & EARN*\n\n"
        f"💵 Reward: *${ref_reward():.4f}* per qualifying referral\n"
        f"👤 Referrals: *{count}*\n\n"
        f"🔗 `{link}`",
        parse_mode="Markdown", reply_markup=back())

async def page_history(q):
    c = db()
    rows = c.execute(
        "SELECT amount,kind FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 20",
        (q.from_user.id,)).fetchall()
    c.close()
    text = "📜 *HISTORY*\n\n"
    text += "\n".join(f"• +${float(x['amount']):.4f} — {x['kind']}" for x in rows) or "No earnings yet."
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=back())

async def page_withdraw(q):
    c = db()
    r = c.execute("SELECT balance FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()
    c.close()
    b = float(r["balance"]) if r else 0
    m = min_withdraw()
    if b < m:
        await q.edit_message_text(
            "💸 *WITHDRAW*\n\n"
            "💳 Payment: *USD*\n"
            "🟡 Network: *BNB Smart Chain (BEP20)*\n"
            f"💰 Balance: *${b:.4f}*\n"
            f"🔒 Minimum: *${m:.2f}*\n\n"
            "❌ Minimum not reached.",
            parse_mode="Markdown", reply_markup=back())
        return
    await q.edit_message_text(
        "💸 *WITHDRAW USD*\n\n"
        "💳 Payment: *USD*\n"
        "🟡 Network: *BNB Smart Chain (BEP20)*\n"
        f"🔒 Minimum: *${m:.2f}*\n\n"
        "Tap the button and then send your BEP20 receiving wallet address.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 ENTER WALLET", callback_data="wallet")],
            [InlineKeyboardButton("🔙 Back", callback_data="home")]
        ]))

async def page_help(q):
    await q.edit_message_text(
        "❓ *HELP*\n\n"
        "🎬 Watch Ads — open available ad\n"
        "💰 Balance — see earnings\n"
        "👥 Referral — invite friends\n"
        "💸 Withdraw — USD to BEP20\n"
        "📜 History — recent earnings\n\n"
        "Minimum withdrawal: $0.50",
        parse_mode="Markdown", reply_markup=back())

# ---------- Wallet: plain message after clicking Enter Wallet ----------
def valid_wallet(s):
    s = s.strip()
    if len(s) != 42 or not s.startswith("0x"):
        return False
    try:
        int(s[2:], 16)
        return True
    except ValueError:
        return False

async def wallet_button(q, context):
    context.user_data["waiting_wallet"] = True
    await q.edit_message_text(
        "📤 *SEND YOUR BEP20 WALLET*\n\n"
        "Now send only your BNB Smart Chain (BEP20) wallet address.\n\n"
        "Example:\n`0x1234567890abcdef1234567890abcdef12345678`",
        parse_mode="Markdown", reply_markup=back())

async def wallet_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_wallet"):
        return
    address = update.message.text.strip()
    if not valid_wallet(address):
        await update.message.reply_text(
            "❌ Invalid BEP20 address.\n\nPlease send a valid 42-character address starting with `0x`.")
        return

    c = db()
    r = c.execute("SELECT balance FROM users WHERE user_id=?", (update.effective_user.id,)).fetchone()
    b = float(r["balance"]) if r else 0
    m = min_withdraw()
    if b < m:
        context.user_data["waiting_wallet"] = False
        c.close()
        await update.message.reply_text(f"❌ Minimum withdrawal is ${m:.2f}.", reply_markup=home())
        return

    cur = c.execute(
        "INSERT INTO withdrawals(user_id,wallet,amount,status) VALUES(?,?,?,'pending')",
        (update.effective_user.id, address, b))
    wid = cur.lastrowid
    c.execute("UPDATE users SET balance=0 WHERE user_id=?", (update.effective_user.id,))
    c.commit()
    c.close()
    context.user_data["waiting_wallet"] = False

    await update.message.reply_text(
        "✅ *WITHDRAWAL SUBMITTED*\n\n"
        f"🧾 Request: `#{wid}`\n"
        f"💵 Amount: *${b:.4f}*\n"
        "🟡 Network: *BNB Smart Chain (BEP20)*\n"
        "⏳ Status: *Pending*\n\n"
        "Payment will be made manually.",
        parse_mode="Markdown", reply_markup=home())

# ---------- Admin ----------
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin access only.")
        return
    await update.message.reply_text(
        "🛠️ *ADMIN DASHBOARD*\n\nEverything is controlled here.",
        parse_mode="Markdown", reply_markup=admin_menu())

async def setadlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    url = update.message.text.partition(" ")[2].strip()
    if not url.startswith(("https://", "http://")):
        await update.message.reply_text("❌ Use: /setadlink https://YOUR-MONETAG-LINK")
        return
    c = db()
    old = c.execute("SELECT id FROM ads WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    if old:
        c.execute("UPDATE ads SET url=?,reward=?,title=? WHERE id=?",
                  (url, ad_reward(), "Monetag Ad", old["id"]))
    else:
        c.execute("INSERT INTO ads(title,url,reward,active) VALUES(?,?,?,1)",
                  ("Monetag Ad", url, ad_reward()))
    c.commit(); c.close()
    await update.message.reply_text(
        f"✅ Monetag link saved.\n💵 Reward: ${ad_reward():.4f}\n🎬 User Ad Center is ready.")

async def setadreward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        v = float(update.message.text.partition(" ")[2].strip())
        if v <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Use: /setadreward 0.0001"); return
    set_setting("ad_reward", v)
    c = db(); c.execute("UPDATE ads SET reward=? WHERE active=1", (v,)); c.commit(); c.close()
    await update.message.reply_text(f"✅ Ad reward: ${v:.4f}")

async def setrefreward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        v = float(update.message.text.partition(" ")[2].strip())
        if v <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Use: /setrefreward 0.001"); return
    set_setting("ref_reward", v)
    await update.message.reply_text(f"✅ Referral reward for future qualifying referrals: ${v:.4f}")

async def setminwithdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        v = float(update.message.text.partition(" ")[2].strip())
        if v <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Use: /setminwithdraw 0.50"); return
    set_setting("min_withdraw", v)
    await update.message.reply_text(f"✅ Minimum withdrawal: ${v:.2f}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    c=db()
    u=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    p=c.execute("SELECT COUNT(*) n FROM withdrawals WHERE status='pending'").fetchone()["n"]
    paid=c.execute("SELECT COUNT(*) n FROM withdrawals WHERE status='paid'").fetchone()["n"]
    bal=c.execute("SELECT COALESCE(SUM(balance),0) n FROM users").fetchone()["n"]
    c.close()
    await update.message.reply_text(
        f"📊 *STATISTICS*\n\n👤 Users: {u}\n⏳ Pending: {p}\n✅ Paid: {paid}\n💰 User balances: ${float(bal):.4f}",
        parse_mode="Markdown")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    c=db(); rows=c.execute(
        "SELECT user_id,username,balance,referral_count FROM users ORDER BY created_at DESC LIMIT 30").fetchall(); c.close()
    text="👥 *RECENT USERS*\n\n"
    for r in rows:
        name="@"+r["username"] if r["username"] else "-"
        text += f"• `{r['user_id']}` {name} — ${float(r['balance']):.4f} — Ref: {r['referral_count']}\n"
    await update.message.reply_text(text or "No users.", parse_mode="Markdown")

async def withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await show_withdrawals_message(update)

async def show_withdrawals_message(update):
    c=db(); rows=c.execute(
        "SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC LIMIT 20").fetchall(); c.close()
    if not rows:
        await update.message.reply_text("💸 *PENDING WITHDRAWALS*\n\nNo pending requests.", parse_mode="Markdown")
        return
    text="💸 *PENDING WITHDRAWALS*\n\n"; buttons=[]
    for r in rows:
        text += f"🧾 *#{r['id']}* | User `{r['user_id']}` | ${float(r['amount']):.4f}\n`{r['wallet']}`\n\n"
        buttons.append([
            InlineKeyboardButton(f"✅ Paid #{r['id']}", callback_data=f"paid:{r['id']}"),
            InlineKeyboardButton(f"❌ Reject #{r['id']}", callback_data=f"reject:{r['id']}")
        ])
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="a_withdrawals")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def show_withdrawals_query(q):
    c=db(); rows=c.execute(
        "SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC LIMIT 20").fetchall(); c.close()
    if not rows:
        await q.edit_message_text("💸 *PENDING WITHDRAWALS*\n\nNo pending requests.",
                                  parse_mode="Markdown", reply_markup=admin_menu()); return
    text="💸 *PENDING WITHDRAWALS*\n\n"; buttons=[]
    for r in rows:
        text += f"🧾 *#{r['id']}* | User `{r['user_id']}` | ${float(r['amount']):.4f}\n`{r['wallet']}`\n\n"
        buttons.append([
            InlineKeyboardButton(f"✅ Paid #{r['id']}", callback_data=f"paid:{r['id']}"),
            InlineKeyboardButton(f"❌ Reject #{r['id']}", callback_data=f"reject:{r['id']}")
        ])
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="a_withdrawals"),
                    InlineKeyboardButton("🏠 Home", callback_data="home")])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def process_withdrawal(q, wid, status):
    if q.from_user.id != ADMIN_ID: return
    c=db(); r=c.execute("SELECT * FROM withdrawals WHERE id=? AND status='pending'", (wid,)).fetchone()
    if not r:
        c.close(); await q.answer("Already processed.", show_alert=True); return
    if status == "rejected":
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r["amount"], r["user_id"]))
    c.execute("UPDATE withdrawals SET status=? WHERE id=?", (status, wid))
    c.commit(); c.close()
    await q.answer(f"#{wid}: {status}")
    await show_withdrawals_query(q)

# ---------- Commands visible in Telegram ----------
async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("balance", "Check your balance"),
        BotCommand("referral", "Open referral page"),
        BotCommand("withdraw", "Withdraw earnings"),
        BotCommand("history", "Earning history"),
        BotCommand("help", "Help")
    ])
    # Telegram supports a different command list for the admin chat.
    try:
        from telegram import BotCommandScopeChat
        await app.bot.set_my_commands([
            BotCommand("start", "Start the bot"),
            BotCommand("admin", "Admin dashboard"),
            BotCommand("setadlink", "Set Monetag ad link"),
            BotCommand("setadreward", "Set ad reward"),
            BotCommand("setrefreward", "Set referral reward"),
            BotCommand("setminwithdraw", "Set minimum withdrawal"),
            BotCommand("stats", "Bot statistics"),
            BotCommand("users", "Recent users"),
            BotCommand("withdrawals", "Pending withdrawals"),
            BotCommand("admincommands", "All admin commands")
        ], scope=BotCommandScopeChat(chat_id=ADMIN_ID))
    except Exception as e:
        print("Admin command scope setup warning:", e)

async def balance_cmd(update, context):
    await register(update.effective_user)
    # Fake query-like object isn't necessary; send direct.
    c=db(); r=c.execute("SELECT balance FROM users WHERE user_id=?", (update.effective_user.id,)).fetchone(); c.close()
    b=float(r["balance"]) if r else 0
    await update.message.reply_text(f"💰 Balance: ${b:.4f}\n🔒 Minimum: ${min_withdraw():.2f}")

async def referral_cmd(update, context):
    await register(update.effective_user)
    me=await context.bot.get_me()
    link=f"https://t.me/{me.username}?start=ref_{update.effective_user.id}"
    await update.message.reply_text(f"👥 Referral reward: ${ref_reward():.4f}\n\n🔗 {link}")

async def withdraw_cmd(update, context):
    # send a simple instruction; actual wallet is collected by button flow.
    await update.message.reply_text(
        f"💸 Minimum withdrawal: ${min_withdraw():.2f}\n"
        "🟡 USD → BNB Smart Chain (BEP20)\n\n"
        "Open the main menu and press Withdraw.")

async def history_cmd(update, context):
    await register(update.effective_user)
    c=db(); rows=c.execute("SELECT amount,kind FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 20",(update.effective_user.id,)).fetchall(); c.close()
    text="📜 HISTORY\n\n"+("\n".join(f"+${float(r['amount']):.4f} — {r['kind']}" for r in rows) or "No earnings yet.")
    await update.message.reply_text(text)

async def help_cmd(update, context):
    await update.message.reply_text("❓ Use /start to open the full menu.\n💸 Withdrawal: USD → BNB Smart Chain (BEP20), minimum $0.50.")

async def admincommands(update, context):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "📖 *ALL ADMIN COMMANDS*\n\n"
        "/admin — dashboard\n"
        "/setadlink URL — add/replace Monetag link\n"
        "/setadreward 0.0001 — ad reward display\n"
        "/setrefreward 0.001 — referral reward\n"
        "/setminwithdraw 0.50 — minimum withdrawal\n"
        "/stats — statistics\n"
        "/users — recent users\n"
        "/withdrawals — pending withdrawals\n"
        "/admincommands — this list\n\n"
        "User payment: USD → BNB Smart Chain (BEP20) only.\n"
        "Minimum default: $0.50.",
        parse_mode="Markdown")

# ---------- Callback ----------
async def callbacks(update, context):
    q=update.callback_query; d=q.data
    if d.startswith("paid:"):
        await q.answer(); await process_withdrawal(q,int(d.split(":")[1]),"paid"); return
    if d.startswith("reject:"):
        await q.answer(); await process_withdrawal(q,int(d.split(":")[1]),"rejected"); return
    await q.answer()

    if d=="home":
        await q.edit_message_text("🌟 *BNB TOKEN MINING*\n\nChoose an option 👇",parse_mode="Markdown",reply_markup=home())
    elif d=="ads": await page_ads(q)
    elif d=="balance": await page_balance(q)
    elif d=="ref": await page_ref(q)
    elif d=="history": await page_history(q)
    elif d=="withdraw": await page_withdraw(q)
    elif d=="wallet": await wallet_button(q,context)
    elif d=="help": await page_help(q)
    elif d=="ad_info":
        await q.edit_message_text("ℹ️ Reward is configured by the admin. A SmartLink click alone is not treated as verified completion.",reply_markup=back())
    elif d=="a_stats":
        c=db(); u=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]; p=c.execute("SELECT COUNT(*) n FROM withdrawals WHERE status='pending'").fetchone()["n"]; paid=c.execute("SELECT COUNT(*) n FROM withdrawals WHERE status='paid'").fetchone()["n"]; c.close()
        await q.edit_message_text(f"📊 *STATISTICS*\n\n👤 Users: {u}\n⏳ Pending: {p}\n✅ Paid: {paid}",parse_mode="Markdown",reply_markup=admin_menu())
    elif d=="a_users":
        c=db(); rows=c.execute("SELECT user_id,username,balance,referral_count FROM users ORDER BY created_at DESC LIMIT 20").fetchall(); c.close()
        text="👥 *USERS*\n\n"+("\n".join(f"`{r['user_id']}` @{r['username'] or '-'} — ${float(r['balance']):.4f}" for r in rows) or "No users.")
        await q.edit_message_text(text,parse_mode="Markdown",reply_markup=admin_menu())
    elif d=="a_ads":
        c=db(); ad=c.execute("SELECT * FROM ads WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone(); c.close()
        status="Configured ✅" if ad else "Not configured ❌"
        await q.edit_message_text(
            f"🎬 *AD SETTINGS*\n\n🔗 Link: {status}\n💵 Reward: ${ad_reward():.4f}\n\n"
            "Set link:\n`/setadlink https://YOUR-MONETAG-LINK`\n\n"
            "Set reward:\n`/setadreward 0.0001`",
            parse_mode="Markdown",reply_markup=admin_menu())
    elif d=="a_withdrawals": await show_withdrawals_query(q)
    elif d=="a_commands":
        await q.edit_message_text(
            "📖 *COMMANDS*\n\n"
            "/admin\n/setadlink URL\n/setadreward 0.0001\n/setrefreward 0.001\n"
            "/setminwithdraw 0.50\n/stats\n/users\n/withdrawals\n/admincommands",
            parse_mode="Markdown",reply_markup=admin_menu())

# ---------- Render health ----------
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","text/plain"); self.end_headers()
        self.wfile.write(b"BNB Token Mining is running.")
    def log_message(self,*args): pass

def health():
    HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),Health).serve_forever()

# ---------- Main ----------
def main():
    db().close()
    threading.Thread(target=health,daemon=True).start()

    app=Application.builder().token(BOT_TOKEN).post_init(setup_commands).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("balance",balance_cmd))
    app.add_handler(CommandHandler("referral",referral_cmd))
    app.add_handler(CommandHandler("withdraw",withdraw_cmd))
    app.add_handler(CommandHandler("history",history_cmd))
    app.add_handler(CommandHandler("help",help_cmd))

    app.add_handler(CommandHandler("admin",admin))
    app.add_handler(CommandHandler("setadlink",setadlink))
    app.add_handler(CommandHandler("setadreward",setadreward))
    app.add_handler(CommandHandler("setrefreward",setrefreward))
    app.add_handler(CommandHandler("setminwithdraw",setminwithdraw))
    app.add_handler(CommandHandler("stats",stats))
    app.add_handler(CommandHandler("users",users))
    app.add_handler(CommandHandler("withdrawals",withdrawals))
    app.add_handler(CommandHandler("admincommands",admincommands))

    app.add_handler(CallbackQueryHandler(callbacks))

    # Only captures normal text when the user has just clicked "Enter Wallet".
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_text))

    print("BNB Token Mining is running...")
    app.run_polling()

if __name__=="__main__":
    main()
