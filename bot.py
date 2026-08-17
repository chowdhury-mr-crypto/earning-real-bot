import os, sqlite3, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5932054746
DB_PATH = "earning_real.db"

DEFAULT_AD_REWARD = 0.0001
DEFAULT_REF_REWARD = 0.001
MIN_WITHDRAW = 1.0

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set.")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0,
        referred_by INTEGER, referral_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,url TEXT,reward REAL,
        active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ad_claims(
        user_id INTEGER,ad_id INTEGER,claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id,ad_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,method TEXT,address TEXT,
        amount REAL,status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount REAL,kind TEXT,
        note TEXT,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.commit()
    return c

def get_setting(k, default):
    c=db()
    r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone()
    if r: v=r["value"]
    else:
        v=str(default)
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v)); c.commit()
    c.close()
    return v

def put_setting(k,v):
    c=db()
    c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v)))
    c.commit(); c.close()

def home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Watch Ads & Earn",callback_data="ads")],
        [InlineKeyboardButton("💰 My Balance",callback_data="balance"),
         InlineKeyboardButton("📜 History",callback_data="history")],
        [InlineKeyboardButton("👥 Refer & Earn",callback_data="ref"),
         InlineKeyboardButton("💸 Withdraw",callback_data="withdraw")],
        [InlineKeyboardButton("❓ Help",callback_data="help")]
    ])

def back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back",callback_data="home"),
                                  InlineKeyboardButton("🏠 Home",callback_data="home")]])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Ad Settings",callback_data="aset"),
         InlineKeyboardButton("📊 Statistics",callback_data="stats")],
        [InlineKeyboardButton("💸 Withdrawals",callback_data="aw"),
         InlineKeyboardButton("👥 Users",callback_data="users")],
        [InlineKeyboardButton("🏠 Home",callback_data="home")]
    ])

async def ensure_user(u, ref=None):
    c=db()
    r=c.execute("SELECT user_id FROM users WHERE user_id=?",(u.id,)).fetchone()
    if not r:
        valid_ref = ref if ref and ref != u.id else None
        c.execute("INSERT INTO users(user_id,username,referred_by) VALUES(?,?,?)",(u.id,u.username or "",valid_ref))
        if valid_ref and c.execute("SELECT user_id FROM users WHERE user_id=?",(valid_ref,)).fetchone():
            reward=float(get_setting("ref_reward",DEFAULT_REF_REWARD))
            c.execute("UPDATE users SET balance=balance+?,referral_count=referral_count+1 WHERE user_id=?",(reward,valid_ref))
            c.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(?,?,?,?)",(valid_ref,reward,"referral","New qualifying referral"))
        c.commit()
    c.close()

async def start(update,context):
    ref=None
    if context.args and context.args[0].startswith("ref_"):
        try: ref=int(context.args[0][4:])
        except: pass
    await ensure_user(update.effective_user,ref)
    await update.message.reply_text(
        "🌟 *Welcome to BNB Token Mining!*\n\n"
        "🎬 Watch available ads\n💰 Earn rewards\n👥 Invite friends\n💸 Request withdrawals\n\n"
        "Choose an option below 👇",parse_mode="Markdown",reply_markup=home())

async def admin(update,context):
    if update.effective_user.id!=ADMIN_ID:
        return await update.message.reply_text("⛔ Admin access only.")
    await update.message.reply_text("🛠️ *Admin Dashboard*\n\nChoose an option:",parse_mode="Markdown",reply_markup=admin_menu())

async def setadlink(update,context):
    if update.effective_user.id!=ADMIN_ID: return
    url=update.message.text.partition(" ")[2].strip()
    if not url.startswith(("http://","https://")):
        return await update.message.reply_text("Use:\n/setadlink https://your-monetag-link")
    c=db()
    r=c.execute("SELECT id FROM ads WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    reward=float(get_setting("ad_reward",DEFAULT_AD_REWARD))
    if r: c.execute("UPDATE ads SET url=?,reward=?,title=? WHERE id=?",(url,reward,"Monetag Ad",r["id"]))
    else: c.execute("INSERT INTO ads(title,url,reward) VALUES(?,?,?)",("Monetag Ad",url,reward))
    c.commit(); c.close()
    await update.message.reply_text(f"✅ Ad link saved.\nCurrent display reward: ${reward:.4f}")

async def setadreward(update,context):
    if update.effective_user.id!=ADMIN_ID:return
    try:
        v=float(update.message.text.partition(" ")[2]); assert v>0
    except:
        return await update.message.reply_text("Use: /setadreward 0.0001")
    put_setting("ad_reward",v)
    await update.message.reply_text(f"✅ Ad reward set to ${v:.4f}")

async def setrefreward(update,context):
    if update.effective_user.id!=ADMIN_ID:return
    try:
        v=float(update.message.text.partition(" ")[2]); assert v>0
    except:
        return await update.message.reply_text("Use: /setrefreward 0.001")
    put_setting("ref_reward",v)
    await update.message.reply_text(f"✅ Referral reward set to ${v:.4f}")

async def setminwithdraw(update,context):
    if update.effective_user.id!=ADMIN_ID:return
    try:
        v=float(update.message.text.partition(" ")[2]); assert v>0
    except:
        return await update.message.reply_text("Use: /setminwithdraw 1")
    put_setting("min_withdraw",v)
    await update.message.reply_text(f"✅ Minimum withdrawal set to ${v:.4f}")

async def ads(q):
    c=db(); a=c.execute("SELECT * FROM ads WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone(); c.close()
    if not a:
        return await q.edit_message_text("🎬 *Ad Center*\n\nNo ad is configured yet.",parse_mode="Markdown",reply_markup=back())
    await q.edit_message_text(
        f"🎬 *Ad Center*\n\n"
        f"💵 Reward shown: *${float(a['reward']):.4f}*\n\n"
        "1️⃣ Open the ad below.\n"
        "2️⃣ Complete the supported ad flow.\n"
        "3️⃣ Verified rewards should only be credited through a supported rewarded integration.\n\n"
        "⚠️ A SmartLink click by itself is not proof of completion.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Open Ad",url=a["url"])],
            [InlineKeyboardButton("ℹ️ Reward Info",callback_data="adinfo")],
            [InlineKeyboardButton("🔙 Back",callback_data="home")]
        ]))

async def balance(q):
    c=db(); r=c.execute("SELECT balance FROM users WHERE user_id=?",(q.from_user.id,)).fetchone(); c.close()
    b=float(r["balance"]) if r else 0
    await q.edit_message_text(f"💰 *My Balance*\n\n💵 Available: *${b:.4f}*\n\nMinimum withdrawal: ${float(get_setting('min_withdraw',MIN_WITHDRAW)):.4f}",parse_mode="Markdown",reply_markup=back())

async def history(q):
    c=db()
    rows=c.execute("SELECT amount,kind,note,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 15",(q.from_user.id,)).fetchall()
    c.close()
    text="📜 *Recent History*\n\n"
    text+="\n".join(f"• +${float(r['amount']):.4f} — {r['kind']}" for r in rows) or "No earnings yet."
    await q.edit_message_text(text,parse_mode="Markdown",reply_markup=back())

async def ref(q):
    me=await q.get_bot().get_me()
    link=f"https://t.me/{me.username}?start=ref_{q.from_user.id}"
    c=db(); r=c.execute("SELECT referral_count FROM users WHERE user_id=?",(q.from_user.id,)).fetchone(); c.close()
    count=r["referral_count"] if r else 0
    reward=float(get_setting("ref_reward",DEFAULT_REF_REWARD))
    await q.edit_message_text(
        f"👥 *Refer & Earn*\n\n"
        f"💵 Reward: *${reward:.4f}* per qualifying referral\n"
        f"👤 Your referrals: *{count}*\n\n"
        f"🔗 Your link:\n`{link}`\n\n"
        "Share your link with friends.",
        parse_mode="Markdown",reply_markup=back())

async def withdraw_page(q):
    methods="🔴 TRX / USDT-TRC20\n🟡 BNB\n🟠 BTC\n🟣 LTC\n💵 USD"
    await q.edit_message_text(
        f"💸 *Withdraw*\n\nSupported methods:\n{methods}\n\n"
        f"Minimum: *${float(get_setting('min_withdraw',MIN_WITHDRAW)):.4f}*\n\n"
        "Submit with:\n`/withdraw METHOD ADDRESS AMOUNT`\n\n"
        "Example:\n`/withdraw TRX TYourWallet 1.00`\n\n"
        "Your request will be marked *Pending*. Payment is handled manually by the admin.",
        parse_mode="Markdown",reply_markup=back())

async def withdraw_cmd(update,context):
    p=update.message.text.split(maxsplit=3)
    if len(p)!=4:return await update.message.reply_text("Use: /withdraw TRX WALLET_ADDRESS 1.00")
    method,address=p[1].upper(),p[2]
    try: amount=float(p[3])
    except: return await update.message.reply_text("❌ Invalid amount.")
    if method not in {"TRX","USDT-TRC20","BNB","BTC","LTC","USD"}: return await update.message.reply_text("❌ Unsupported method.")
    minimum=float(get_setting("min_withdraw",MIN_WITHDRAW))
    if amount<minimum:return await update.message.reply_text(f"❌ Minimum withdrawal is ${minimum:.4f}.")
    c=db(); r=c.execute("SELECT balance FROM users WHERE user_id=?",(update.effective_user.id,)).fetchone()
    if not r or float(r["balance"])<amount:c.close();return await update.message.reply_text("❌ Insufficient balance.")
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(amount,update.effective_user.id))
    cur=c.execute("INSERT INTO withdrawals(user_id,method,address,amount) VALUES(?,?,?,?)",(update.effective_user.id,method,address,amount))
    wid=cur.lastrowid
    c.commit(); c.close()
    await update.message.reply_text(f"✅ Withdrawal request #{wid} submitted.\n\nStatus: *Pending* ⏳",parse_mode="Markdown")

async def callbacks(update,context):
    q=update.callback_query; await q.answer(); d=q.data
    if d=="home": await q.edit_message_text("🌟 *BNB Token Mining*\n\nChoose an option 👇",parse_mode="Markdown",reply_markup=home())
    elif d=="ads": await ads(q)
    elif d=="balance": await balance(q)
    elif d=="history": await history(q)
    elif d=="ref": await ref(q)
    elif d=="withdraw": await withdraw_page(q)
    elif d=="help": await q.edit_message_text("❓ *Help*\n\nUse the menu to watch ads, check balance, refer friends and request withdrawals.\n\nFor support, contact the administrator.",parse_mode="Markdown",reply_markup=back())
    elif d=="adinfo": await q.edit_message_text("ℹ️ SmartLink clicks are not automatically treated as verified ad completion. For real rewards, connect Monetag's supported rewarded Telegram Mini App integration.",reply_markup=back())
    elif d=="aset": await q.edit_message_text(
        "🎬 *Ad Settings*\n\n"
        f"Ad reward: ${float(get_setting('ad_reward',DEFAULT_AD_REWARD)):.4f}\n"
        f"Referral reward: ${float(get_setting('ref_reward',DEFAULT_REF_REWARD)):.4f}\n"
        f"Minimum withdrawal: ${float(get_setting('min_withdraw',MIN_WITHDRAW)):.4f}\n\n"
        "`/setadlink URL`\n`/setadreward 0.0001`\n`/setrefreward 0.001`\n`/setminwithdraw 1`",
        parse_mode="Markdown",reply_markup=admin_menu())
    elif d=="stats":
        c=db();u=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"];w=c.execute("SELECT COUNT(*) n FROM withdrawals WHERE status='pending'").fetchone()["n"];b=c.execute("SELECT COALESCE(SUM(balance),0) s FROM users").fetchone()["s"];c.close()
        await q.edit_message_text(f"📊 *Statistics*\n\n👤 Users: {u}\n💸 Pending withdrawals: {w}\n💰 User balances: ${float(b):.4f}",parse_mode="Markdown",reply_markup=admin_menu())
    elif d=="users":
        c=db();rows=c.execute("SELECT user_id,username,balance FROM users ORDER BY created_at DESC LIMIT 20").fetchall();c.close()
        text="👥 *Recent Users*\n\n" + ("\n".join(f"• {r['user_id']} @{r['username'] or '-'} — ${float(r['balance']):.4f}" for r in rows) or "No users.")
        await q.edit_message_text(text,parse_mode="Markdown",reply_markup=admin_menu())
    elif d=="aw":
        c=db();rows=c.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC LIMIT 10").fetchall();c.close()
        if not rows:
            text="💸 *Withdrawals*\n\nNo pending requests."
            kb=admin_menu()
        else:
            text="💸 *Pending Withdrawals*\n\n"
            buttons=[]
            for r in rows:
                text+=f"#{r['id']} • {r['method']} • ${float(r['amount']):.4f}\nUser: {r['user_id']}\nAddress: {r['address']}\n\n"
                buttons.append([InlineKeyboardButton(f"✅ Mark Paid #{r['id']}",callback_data=f"paid:{r['id']}"),
                                InlineKeyboardButton(f"❌ Reject #{r['id']}",callback_data=f"reject:{r['id']}")])
            buttons.append([InlineKeyboardButton("🏠 Home",callback_data="home")])
            kb=InlineKeyboardMarkup(buttons)
        await q.edit_message_text(text,parse_mode="Markdown",reply_markup=kb)
    elif d.startswith("paid:"): await withdrawal_status(q,int(d.split(":")[1]),"paid")
    elif d.startswith("reject:"): await withdrawal_status(q,int(d.split(":")[1]),"rejected")

async def withdrawal_status(q,wid,status):
    if q.from_user.id!=ADMIN_ID:return
    c=db();r=c.execute("SELECT * FROM withdrawals WHERE id=? AND status='pending'",(wid,)).fetchone()
    if not r:c.close();return await q.answer("Request not found or already processed.",show_alert=True)
    if status=="rejected":
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(r["amount"],r["user_id"]))
    c.execute("UPDATE withdrawals SET status=? WHERE id=?",(status,wid));c.commit();c.close()
    await q.answer(f"Request #{wid} marked {status}.")
    await callbacks(update_from_query(q,"aw"),None)

class DummyUpdate:
    def __init__(self,q): self.callback_query=q
def update_from_query(q,data):
    q.data=data
    return DummyUpdate(q)

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header("Content-Type","text/plain");self.end_headers();self.wfile.write(b"BNB Token Mining is running.")
    def log_message(self,*a):pass

def main():
    db().close()
    threading.Thread(target=lambda:HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),Health).serve_forever(),daemon=True).start()
    app=Application.builder().token(BOT_TOKEN).build()
    for name,fn in [("start",start),("admin",admin),("setadlink",setadlink),("setadreward",setadreward),("setrefreward",setrefreward),("setminwithdraw",setminwithdraw),("withdraw",withdraw_cmd)]:
        app.add_handler(CommandHandler(name,fn))
    app.add_handler(CallbackQueryHandler(callbacks))
    print("BNB Token Mining bot is running...")
    app.run_polling()

if __name__=="__main__":main()
