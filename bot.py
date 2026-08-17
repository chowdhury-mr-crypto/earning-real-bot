import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5932054746
DB_PATH = "earning_real.db"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set.")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        referred_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        reward INTEGER NOT NULL,
        url TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS task_claims (
        user_id INTEGER NOT NULL,
        task_id INTEGER NOT NULL,
        claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, task_id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        kind TEXT NOT NULL,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Tasks", callback_data="tasks"),
         InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("👥 Referral", callback_data="referral"),
         InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

def back_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="home"),
         InlineKeyboardButton("🏠 Home", callback_data="home")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Task", callback_data="admin_add"),
         InlineKeyboardButton("📋 Tasks", callback_data="admin_tasks")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🏠 Home", callback_data="home")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    row = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not row:
        conn.execute("INSERT INTO users(user_id, username) VALUES (?,?)",
                     (user.id, user.username or ""))
        conn.commit()
    conn.close()
    await update.message.reply_text(
        "🎉 Welcome to BNB Token Mining!\n\nChoose an option below:",
        reply_markup=main_menu()
    )

async def show_tasks(query):
    conn = get_db()
    tasks = conn.execute("SELECT * FROM tasks WHERE active=1 ORDER BY id DESC").fetchall()
    claimed = {r["task_id"] for r in conn.execute(
        "SELECT task_id FROM task_claims WHERE user_id=?", (query.from_user.id,)
    ).fetchall()}
    conn.close()

    buttons = []
    text = "📋 *Available Tasks*\n\n"
    if not tasks:
        text += "No tasks are available right now."
    else:
        for t in tasks:
            status = "✅ Completed" if t["id"] in claimed else f"💰 {t['reward']} points"
            text += f"*{t['title']}*\n{status}\n\n"
            if t["id"] not in claimed:
                buttons.append([InlineKeyboardButton(
                    f"▶️ Open: {t['title'][:30]}",
                    url=t["url"]
                )])
                buttons.append([InlineKeyboardButton(
                    f"✅ Claim {t['reward']} points",
                    callback_data=f"claim:{t['id']}"
                )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="home")])
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def claim_task(query, task_id):
    conn = get_db()
    task = conn.execute("SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)).fetchone()
    if not task:
        conn.close()
        await query.answer("Task is no longer available.", show_alert=True)
        return
    try:
        conn.execute("INSERT INTO task_claims(user_id, task_id) VALUES (?,?)",
                     (query.from_user.id, task_id))
    except sqlite3.IntegrityError:
        conn.close()
        await query.answer("You already claimed this task.", show_alert=True)
        return
    conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?",
                 (task["reward"], query.from_user.id))
    conn.execute("INSERT INTO transactions(user_id, amount, kind, note) VALUES (?,?,?,?)",
                 (query.from_user.id, task["reward"], "task", task["title"]))
    conn.commit()
    conn.close()
    await query.answer(f"+{task['reward']} points added!", show_alert=True)
    await show_balance(query)

async def show_balance(query):
    conn = get_db()
    row = conn.execute("SELECT balance FROM users WHERE user_id=?", (query.from_user.id,)).fetchone()
    conn.close()
    balance = row["balance"] if row else 0
    await query.edit_message_text(
        f"💰 *Your Balance*\n\n`{balance}` points",
        parse_mode="Markdown", reply_markup=back_home()
    )

async def show_referral(query):
    bot = await query.get_bot()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{query.from_user.id}"
    await query.edit_message_text(
        f"👥 *Referral Program*\n\nYour referral link:\n`{link}`\n\n"
        "Share this link with friends.",
        parse_mode="Markdown", reply_markup=back_home()
    )

async def show_withdraw(query):
    await query.edit_message_text(
        "💸 *Withdraw*\n\nWithdrawal requests are not connected to a real payment provider yet.\n"
        "Your balance is shown for testing only.\n\n"
        "A real payout system will be added after a legitimate payment provider is connected.",
        parse_mode="Markdown", reply_markup=back_home()
    )

async def show_help(query):
    await query.edit_message_text(
        "ℹ️ *Help*\n\n"
        "📋 Tasks — view available tasks\n"
        "💰 Balance — view your points\n"
        "👥 Referral — get your referral link\n"
        "💸 Withdraw — payout section\n\n"
        "Use 🔙 Back or 🏠 Home to return.",
        parse_mode="Markdown", reply_markup=back_home()
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    await update.message.reply_text("🛠️ *Admin Panel*", parse_mode="Markdown",
                                    reply_markup=admin_menu())

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = get_db()
    users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    tasks = conn.execute("SELECT COUNT(*) c FROM tasks WHERE active=1").fetchone()["c"]
    balance = conn.execute("SELECT COALESCE(SUM(balance),0) s FROM users").fetchone()["s"]
    conn.close()
    await update.message.reply_text(
        f"📊 *Stats*\n\nUsers: {users}\nActive tasks: {tasks}\nTotal points: {balance}",
        parse_mode="Markdown", reply_markup=admin_menu()
    )

async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    raw = update.message.text.partition(" ")[2].strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await update.message.reply_text(
            "Use:\n/addtask Title | reward | https://example.com")
        return
    title, reward, url = parts
    try:
        reward = int(reward)
        if reward <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Reward must be a positive whole number.")
        return
    conn = get_db()
    cur = conn.execute("INSERT INTO tasks(title,reward,url) VALUES (?,?,?)",
                       (title, reward, url))
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    await update.message.reply_text(f"✅ Task #{task_id} added.")

async def deltask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    raw = update.message.text.partition(" ")[2].strip()
    try:
        task_id = int(raw)
    except ValueError:
        await update.message.reply_text("Use: /deltask TASK_ID")
        return
    conn = get_db()
    conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Task #{task_id} deactivated.")

async def tasksadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = get_db()
    tasks = conn.execute("SELECT * FROM tasks WHERE active=1 ORDER BY id DESC").fetchall()
    conn.close()
    if not tasks:
        text = "No active tasks."
    else:
        text = "\n".join(f"#{t['id']} — {t['title']} — {t['reward']} points" for t in tasks)
    await update.message.reply_text("📋 *Active Tasks*\n\n" + text,
                                    parse_mode="Markdown", reply_markup=admin_menu())

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "home":
        await query.edit_message_text(
            "🏠 *BNB Token Mining*\n\nChoose an option:",
            parse_mode="Markdown", reply_markup=main_menu())
    elif data == "tasks":
        await show_tasks(query)
    elif data == "balance":
        await show_balance(query)
    elif data == "referral":
        await show_referral(query)
    elif data == "withdraw":
        await show_withdraw(query)
    elif data == "help":
        await show_help(query)
    elif data.startswith("claim:"):
        await claim_task(query, int(data.split(":")[1]))
    elif data == "admin_add":
        await query.edit_message_text(
            "➕ Add a task\n\nSend:\n"
            "`/addtask Title | reward | https://example.com`",
            parse_mode="Markdown", reply_markup=back_home())
    elif data == "admin_tasks":
        conn = get_db()
        tasks = conn.execute("SELECT * FROM tasks WHERE active=1 ORDER BY id DESC").fetchall()
        conn.close()
        text = "📋 *Active Tasks*\n\n"
        text += "\n".join(f"#{t['id']} — {t['title']} — {t['reward']} points" for t in tasks) or "No active tasks."
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=admin_menu())
    elif data == "admin_stats":
        conn = get_db()
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        tasks = conn.execute("SELECT COUNT(*) c FROM tasks WHERE active=1").fetchone()["c"]
        balance = conn.execute("SELECT COALESCE(SUM(balance),0) s FROM users").fetchone()["s"]
        conn.close()
        await query.edit_message_text(
            f"📊 *Stats*\n\nUsers: {users}\nActive tasks: {tasks}\nTotal points: {balance}",
            parse_mode="Markdown", reply_markup=admin_menu())

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"BNB Token Mining bot is running.")

    def log_message(self, format, *args):
        pass

def health_server():
    port = int(os.getenv("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

def main():
    get_db().close()
    threading.Thread(target=health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("deltask", deltask))
    app.add_handler(CommandHandler("tasksadmin", tasksadmin))
    app.add_handler(CallbackQueryHandler(callbacks))
    print("BNB Token Mining bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
