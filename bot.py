import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
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

def ensure_user(user):
    con = db()
    row = con.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not row:
        con.execute(
            "INSERT INTO users(user_id, username) VALUES (?, ?)",
            (user.id, user.username or "")
        )
        con.commit()
    con.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    kb = [
        [InlineKeyboardButton("📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("👥 Referral", callback_data="referral")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    await update.message.reply_text(
        "🎉 Welcome to Earning Real!\n\n"
        "Complete genuine sponsored tasks and earn rewards.\n"
        "No fake balance and no deposit required.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "balance":
        con = db()
        bal = con.execute("SELECT balance FROM users WHERE user_id=?",
                           (q.from_user.id,)).fetchone()[0]
        con.close()
        await q.edit_message_text(f"💰 Your balance: {bal} points")
    elif q.data == "referral":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start={q.from_user.id}"
        con = db()
        refs = con.execute("SELECT referrals FROM users WHERE user_id=?",
                           (q.from_user.id,)).fetchone()[0]
        con.close()
        await q.edit_message_text(
            f"👥 Referrals: {refs}\n\nYour referral link:\n{link}"
        )
    elif q.data == "tasks":
        con = db()
        tasks = con.execute(
            "SELECT id,title,reward,url FROM tasks WHERE active=1 ORDER BY id"
        ).fetchall()
        con.close()
        if not tasks:
            await q.edit_message_text(
                "📋 No sponsored tasks are available right now.\n"
                "Check again later."
            )
            return
        buttons = [
            [InlineKeyboardButton(f"{title} — +{reward} points",
                                  callback_data=f"task:{tid}")]
            for tid, title, reward, url in tasks
        ]
        await q.edit_message_text("📋 Available tasks:",
                                  reply_markup=InlineKeyboardMarkup(buttons))
    elif q.data == "withdraw":
        await q.edit_message_text(
            "💸 Withdrawal is not enabled in this demo yet.\n\n"
            "When real sponsor revenue and a verified payment method are connected, "
            "we can add minimum-balance and withdrawal verification."
        )

async def task_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = int(q.data.split(":")[1])
    con = db()
    task = con.execute(
        "SELECT title,reward,url FROM tasks WHERE id=? AND active=1", (tid,)
    ).fetchone()
    if not task:
        con.close()
        await q.edit_message_text("This task is no longer available.")
        return
    done = con.execute(
        "SELECT 1 FROM completions WHERE user_id=? AND task_id=?",
        (q.from_user.id, tid)
    ).fetchone()
    if done:
        con.close()
        await q.edit_message_text("✅ You already completed this task.")
        return
    title, reward, url = task
    con.close()
    await q.edit_message_text(
        f"📋 {title}\n\n"
        f"Reward: +{reward} points\n\n"
        f"Open the task link, complete the sponsor's required action, "
        f"then return to the bot. Automatic verification is not included "
        f"in this demo.\n\n{url}"
    )

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Earning Real bot is running!")

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

    # Render Web Services require an HTTP port to be open.
    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(task_click, pattern=r"^task:\d+$"))
    app.add_handler(CallbackQueryHandler(menu))

    print("Earning Real bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
