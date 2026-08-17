import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5932054746"))
REFERRAL_BONUS = 10
DB = "earning_real.db"


def db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        referred_by INTEGER
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        reward INTEGER NOT NULL,
        url TEXT NOT NULL,
        active INTEGER DEFAULT 1
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS completions(
        user_id INTEGER,
        task_id INTEGER,
        PRIMARY KEY(user_id, task_id)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        wallet TEXT,
        status TEXT DEFAULT 'pending'
    )""")
    con.commit()
    return con


def ensure_user(user, referred_by=None):
    con = db()
    row = con.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not row:
        valid_ref = None
        if referred_by and referred_by != user.id:
            ref_exists = con.execute("SELECT user_id FROM users WHERE user_id=?", (referred_by,)).fetchone()
            if ref_exists:
                valid_ref = referred_by
        con.execute(
            "INSERT INTO users(user_id, username, referred_by) VALUES (?, ?, ?)",
            (user.id, user.username or "", valid_ref)
        )
        if valid_ref:
            con.execute("UPDATE users SET referrals=referrals+1, balance=balance+? WHERE user_id=?", (REFERRAL_BONUS, valid_ref))
    else:
        con.execute("UPDATE users SET username=? WHERE user_id=?", (user.username or "", user.id))
    con.commit()
    con.close()


def is_admin(user_id):
    return user_id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
        except ValueError:
            pass
    ensure_user(update.effective_user, ref)
    kb = [
        [InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("👥 Referral", callback_data="referral")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    if is_admin(update.effective_user.id):
        kb.append([InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin")])
    await update.message.reply_text(
        "🎉 Welcome to BNB Token Mining!\n\n"
        "Complete genuine sponsored tasks and earn rewards.\n"
        "No fake balance and no deposit required.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin access only.")
        return
    await update.message.reply_text(
        "🛠️ Admin Panel\n\n"
        "/addtask Title | reward | URL\n"
        "/deltask ID\n"
        "/tasksadmin — list tasks\n"
        "/stats — bot statistics\n\n"
        "Example:\n/addtask Visit Sponsor | 25 | https://example.com"
    )


async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin access only.")
        return
    raw = update.message.text.partition(" ")[2].strip()
    parts = [p.strip() for p in raw.split("|", 2)]
    if len(parts) != 3:
        await update.message.reply_text("Format:\n/addtask Title | reward | URL")
        return
    title, reward_text, url = parts
    try:
        reward = int(reward_text)
        if reward <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Reward must be a positive whole number.")
        return
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("URL must start with http:// or https://")
        return
    con = db()
    cur = con.execute("INSERT INTO tasks(title,reward,url,active) VALUES(?,?,?,1)", (title, reward, url))
    con.commit()
    task_id = cur.lastrowid
    con.close()
    await update.message.reply_text(f"✅ Task added. ID: {task_id}\nReward: {reward} points")


async def deltask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin access only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /deltask ID")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Task ID must be a number.")
        return
    con = db()
    cur = con.execute("UPDATE tasks SET active=0 WHERE id=?", (tid,))
    con.commit()
    con.close()
    await update.message.reply_text("✅ Task disabled." if cur.rowcount else "❌ Task not found.")


async def tasksadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin access only.")
        return
    con = db()
    rows = con.execute("SELECT id,title,reward,url,active FROM tasks ORDER BY id DESC").fetchall()
    con.close()
    if not rows:
        await update.message.reply_text("No tasks yet.")
        return
    lines = [f"#{r[0]} | {r[1]} | +{r[2]} | {'ON' if r[4] else 'OFF'}\n{r[3]}" for r in rows]
    await update.message.reply_text("🧾 Tasks\n\n" + "\n\n".join(lines))


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin access only.")
        return
    con = db()
    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    tasks = con.execute("SELECT COUNT(*) FROM tasks WHERE active=1").fetchone()[0]
    completions = con.execute("SELECT COUNT(*) FROM completions").fetchone()[0]
    pending = con.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0]
    con.close()
    await update.message.reply_text(
        f"📊 Stats\n\nUsers: {users}\nActive tasks: {tasks}\nTask completions: {completions}\nPending withdrawals: {pending}"
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ensure_user(q.from_user)
    if q.data == "balance":
        con = db()
        bal = con.execute("SELECT balance FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
        con.close()
        await q.edit_message_text(f"💰 Your balance: {bal} points")
    elif q.data == "referral":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start={q.from_user.id}"
        con = db()
        refs = con.execute("SELECT referrals FROM users WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
        con.close()
        await q.edit_message_text(f"👥 Referrals: {refs}\n\nReferral bonus: {REFERRAL_BONUS} points per valid referral.\n\nYour link:\n{link}")
    elif q.data == "tasks":
        con = db()
        tasks = con.execute("SELECT id,title,reward FROM tasks WHERE active=1 ORDER BY id").fetchall()
        con.close()
        if not tasks:
            await q.edit_message_text("📋 No sponsored tasks are available right now.")
            return
        buttons = [[InlineKeyboardButton(f"{title} — +{reward} points", callback_data=f"task:{tid}")] for tid, title, reward in tasks]
        await q.edit_message_text("📋 Available tasks:", reply_markup=InlineKeyboardMarkup(buttons))
    elif q.data == "withdraw":
        await q.edit_message_text("💸 Withdrawal is not enabled yet. Real sponsor revenue and verified payout processing must be connected first.")
    elif q.data == "admin":
        if not is_admin(q.from_user.id):
            await q.edit_message_text("⛔ Admin access only.")
            return
        await q.edit_message_text("🛠️ Admin commands:\n/addtask Title | reward | URL\n/deltask ID\n/tasksadmin\n/stats")


async def task_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = int(q.data.split(":")[1])
    con = db()
    task = con.execute("SELECT title,reward,url FROM tasks WHERE id=? AND active=1", (tid,)).fetchone()
    if not task:
        con.close()
        await q.edit_message_text("This task is no longer available.")
        return
    done = con.execute("SELECT 1 FROM completions WHERE user_id=? AND task_id=?", (q.from_user.id, tid)).fetchone()
    con.close()
    if done:
        await q.edit_message_text("✅ You already completed this task.")
        return
    title, reward, url = task
    await q.edit_message_text(
        f"📋 {title}\n\nReward: +{reward} points\n\n"
        "Open the task link and complete the sponsor's required action. "
        "Automatic external-task verification is not included yet, so this button does not credit the reward automatically.\n\n"
        f"{url}"
    )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"BNB Token Mining bot is running!")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server listening on port {port}...")
    server.serve_forever()


def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise SystemExit("Set BOT_TOKEN in your environment before running.")
    db().close()
    threading.Thread(target=start_health_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("deltask", deltask))
    app.add_handler(CommandHandler("tasksadmin", tasksadmin))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(task_click, pattern=r"^task:\d+$"))
    app.add_handler(CallbackQueryHandler(menu))
    print("BNB Token Mining bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
