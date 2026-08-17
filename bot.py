import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)

# =========================
# BASIC CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5932054746

DB_PATH = "earning_real.db"

# Default values requested for this bot
AD_REWARD = 0.0001
REF_REWARD = 0.001
MIN_WITHDRAW = 0.50

WALLET_WAIT = 1

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable BOT_TOKEN is missing.")


# =========================
# DATABASE
# =========================
def db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            reward REAL NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            wallet TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            kind TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def get_setting(key, default):
    conn = db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()

    if row:
        value = row["value"]
    else:
        value = str(default)
        conn.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
            (key, value)
        )
        conn.commit()

    conn.close()
    return value


def set_setting(key, value):
    conn = db()
    conn.execute("""
        INSERT INTO settings(key,value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()


def ad_reward():
    return float(get_setting("ad_reward", AD_REWARD))


def ref_reward():
    return float(get_setting("ref_reward", REF_REWARD))


def min_withdraw():
    return float(get_setting("min_withdraw", MIN_WITHDRAW))


# =========================
# KEYBOARDS
# =========================
def home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Watch Ads & Earn", callback_data="ads")],
        [
            InlineKeyboardButton("💰 My Balance", callback_data="balance"),
            InlineKeyboardButton("👥 Refer & Earn", callback_data="ref")
        ],
        [
            InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
            InlineKeyboardButton("📜 History", callback_data="history")
        ],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Back", callback_data="home"),
            InlineKeyboardButton("🏠 Home", callback_data="home")
        ]
    ])


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Users", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("🎬 Ad Settings", callback_data="admin_ads"),
            InlineKeyboardButton("💸 Withdrawals", callback_data="admin_withdrawals")
        ],
        [
            InlineKeyboardButton("📖 Admin Commands", callback_data="admin_commands")
        ],
        [InlineKeyboardButton("🏠 Home", callback_data="home")]
    ])


def withdrawal_admin_keyboard(rows):
    buttons = []
    for row in rows:
        buttons.append([
            InlineKeyboardButton(
                f"✅ Paid #{row['id']}",
                callback_data=f"paid:{row['id']}"
            ),
            InlineKeyboardButton(
                f"❌ Reject #{row['id']}",
                callback_data=f"reject:{row['id']}"
            )
        ])

    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_withdrawals")])
    buttons.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
    return InlineKeyboardMarkup(buttons)


# =========================
# USER REGISTRATION / REFERRAL
# =========================
async def ensure_user(user, ref_id=None):
    conn = db()

    existing = conn.execute(
        "SELECT user_id FROM users WHERE user_id = ?", (user.id,)
    ).fetchone()

    if not existing:
        valid_ref = None

        if ref_id and ref_id != user.id:
            ref_exists = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?", (ref_id,)
            ).fetchone()
            if ref_exists:
                valid_ref = ref_id

        conn.execute(
            "INSERT INTO users(user_id,username,referred_by) VALUES(?,?,?)",
            (user.id, user.username or "", valid_ref)
        )

        # Referral reward is given once when a new qualifying user joins.
        if valid_ref:
            reward = ref_reward()

            conn.execute(
                "UPDATE users SET balance = balance + ?, referral_count = referral_count + 1 WHERE user_id = ?",
                (reward, valid_ref)
            )

            conn.execute(
                "INSERT INTO transactions(user_id,amount,kind,note) VALUES(?,?,?,?)",
                (
                    valid_ref,
                    reward,
                    "referral",
                    "Qualifying referral"
                )
            )

        conn.commit()
    else:
        conn.execute(
            "UPDATE users SET username=? WHERE user_id=?",
            (user.username or "", user.id)
        )
        conn.commit()

    conn.close()


# =========================
# /start
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ref_id = None

    if context.args:
        value = context.args[0]
        if value.startswith("ref_"):
            try:
                ref_id = int(value[4:])
            except ValueError:
                pass

    await ensure_user(update.effective_user, ref_id)

    await update.message.reply_text(
        "🌟 *Welcome to BNB Token Mining!*\n\n"
        "🎬 Watch available ads\n"
        "💰 Earn rewards\n"
        "👥 Invite friends\n"
        "💸 Withdraw to your BEP20 wallet\n\n"
        "Choose an option below 👇",
        parse_mode="Markdown",
        reply_markup=home_keyboard()
    )


# =========================
# USER PAGES
# =========================
async def show_ads(query):
    conn = db()
    ad = conn.execute("""
        SELECT * FROM ads
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()
    conn.close()

    if not ad:
        await query.edit_message_text(
            "🎬 *Ad Center*\n\n"
            "No ad is configured yet.\n\n"
            "Please check again later.",
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )
        return

    await query.edit_message_text(
        "🎬 *Watch Ads & Earn*\n\n"
        f"💵 Displayed reward: *${float(ad['reward']):.4f}*\n\n"
        "Tap the button below to open the available ad.\n\n"
        "⚠️ A SmartLink click by itself is not treated as verified ad completion. "
        "Verified rewarded advertising should use the supported rewarded integration.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Open Ad", url=ad["url"])],
            [InlineKeyboardButton("ℹ️ Reward Info", callback_data="ad_info")],
            [InlineKeyboardButton("🔙 Back", callback_data="home")]
        ])
    )


async def show_balance(query):
    conn = db()
    row = conn.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (query.from_user.id,)
    ).fetchone()
    conn.close()

    balance = float(row["balance"]) if row else 0.0

    await query.edit_message_text(
        "💰 *My Balance*\n\n"
        f"💵 Available: *${balance:.4f}*\n"
        f"💸 Minimum withdrawal: *${min_withdraw():.2f}*\n\n"
        "🟡 Withdrawal network: *BNB Smart Chain (BEP20)*",
        parse_mode="Markdown",
        reply_markup=back_keyboard()
    )


async def show_referral(query):
    bot = await query.get_bot().get_me()
    link = f"https://t.me/{bot.username}?start=ref_{query.from_user.id}"

    conn = db()
    row = conn.execute(
        "SELECT referral_count FROM users WHERE user_id=?",
        (query.from_user.id,)
    ).fetchone()
    conn.close()

    count = int(row["referral_count"]) if row else 0

    await query.edit_message_text(
        "👥 *Refer & Earn*\n\n"
        f"💵 Reward: *${ref_reward():.4f}* per qualifying referral\n"
        f"👤 Your referrals: *{count}*\n\n"
        "🔗 *Your referral link:*\n"
        f"`{link}`\n\n"
        "Share this link with your friends.",
        parse_mode="Markdown",
        reply_markup=back_keyboard()
    )


async def show_history(query):
    conn = db()
    rows = conn.execute("""
        SELECT amount,kind,note,created_at
        FROM transactions
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 15
    """, (query.from_user.id,)).fetchall()
    conn.close()

    if not rows:
        text = "📜 *Earning History*\n\nNo earnings yet."
    else:
        lines = []
        for row in rows:
            lines.append(
                f"• +${float(row['amount']):.4f} — {row['kind']}"
            )
        text = "📜 *Earning History*\n\n" + "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_keyboard()
    )


async def show_withdraw(query):
    conn = db()
    row = conn.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (query.from_user.id,)
    ).fetchone()
    conn.close()

    balance = float(row["balance"]) if row else 0.0
    minimum = min_withdraw()

    if balance < minimum:
        await query.edit_message_text(
            "💸 *Withdraw*\n\n"
            "💳 Payment: *USD*\n"
            "🟡 Network: *BNB Smart Chain (BEP20)*\n\n"
            f"💰 Your balance: *${balance:.4f}*\n"
            f"🔒 Minimum withdrawal: *${minimum:.2f}*\n\n"
            "❌ You have not reached the minimum withdrawal amount yet.",
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )
        return

    await query.edit_message_text(
        "💸 *Withdraw*\n\n"
        "💳 Payment: *USD*\n"
        "🟡 Network: *BNB Smart Chain (BEP20)*\n"
        f"🔒 Minimum: *${minimum:.2f}*\n\n"
        "When you continue, you will provide only your "
        "*BEP20 receiving wallet address*.\n\n"
        "⚠️ Make sure the address supports BNB Smart Chain (BEP20).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Enter Wallet", callback_data="wallet_prompt")],
            [InlineKeyboardButton("🔙 Back", callback_data="home")]
        ])
    )


async def wallet_prompt(query):
    await query.edit_message_text(
        "📤 *BEP20 Wallet Address*\n\n"
        "Send only your BNB Smart Chain (BEP20) receiving address.\n\n"
        "It should normally start with `0x` and contain 42 characters.",
        parse_mode="Markdown",
        reply_markup=back_keyboard()
    )


async def help_page(query):
    await query.edit_message_text(
        "❓ *How to use the bot*\n\n"
        "🎬 *Watch Ads* — open available ads.\n"
        "💰 *Balance* — see your earnings.\n"
        "👥 *Referral* — invite friends and earn.\n"
        "💸 *Withdraw* — available from $0.50 to a BEP20 wallet.\n"
        "📜 *History* — see recent earnings.\n\n"
        "For support, contact the administrator.",
        parse_mode="Markdown",
        reply_markup=back_keyboard()
    )


# =========================
# WALLET / WITHDRAWAL
# =========================
def valid_bep20(address):
    if not address.startswith("0x"):
        return False
    if len(address) != 42:
        return False

    try:
        int(address[2:], 16)
        return True
    except ValueError:
        return False


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.partition(" ")[2].strip()

    if not valid_bep20(address):
        await update.message.reply_text(
            "❌ Invalid BEP20 wallet address.\n\n"
            "Use:\n"
            "`/wallet 0xYOUR_BEP20_ADDRESS`",
            parse_mode="Markdown"
        )
        return

    conn = db()
    row = conn.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (update.effective_user.id,)
    ).fetchone()

    balance = float(row["balance"]) if row else 0.0
    minimum = min_withdraw()

    if balance < minimum:
        conn.close()
        await update.message.reply_text(
            f"❌ Minimum withdrawal is ${minimum:.2f}."
        )
        return

    cur = conn.execute("""
        INSERT INTO withdrawals(user_id,wallet,amount,status)
        VALUES(?,?,?,'pending')
    """, (update.effective_user.id, address, balance))

    withdrawal_id = cur.lastrowid

    conn.execute(
        "UPDATE users SET balance=0 WHERE user_id=?",
        (update.effective_user.id,)
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        "✅ *Withdrawal Request Submitted!*\n\n"
        f"🧾 Request: `#{withdrawal_id}`\n"
        f"💵 Amount: *${balance:.4f}*\n"
        "🟡 Network: *BNB Smart Chain (BEP20)*\n"
        "⏳ Status: *Pending*\n\n"
        "Payment will be processed manually.",
        parse_mode="Markdown"
    )


# =========================
# ADMIN
# =========================
def is_admin(user_id):
    return user_id == ADMIN_ID


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin access only.")
        return

    await update.message.reply_text(
        "🛠️ *Admin Dashboard*\n\n"
        "Everything needed to operate the bot is available below.",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )


async def setadlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    url = update.message.text.partition(" ")[2].strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text(
            "❌ Invalid link.\n\n"
            "Use:\n"
            "`/setadlink https://YOUR-MONETAG-LINK`",
            parse_mode="Markdown"
        )
        return

    conn = db()

    existing = conn.execute("""
        SELECT id FROM ads
        WHERE active=1
        ORDER BY id DESC LIMIT 1
    """).fetchone()

    if existing:
        conn.execute(
            "UPDATE ads SET url=?,reward=?,title=? WHERE id=?",
            (url, ad_reward(), "Monetag Ad", existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO ads(title,url,reward,active) VALUES(?,?,?,1)",
            ("Monetag Ad", url, ad_reward())
        )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        "✅ *Monetag Ad Link Saved!*\n\n"
        f"💵 Display reward: ${ad_reward():.4f}\n"
        "🎬 It is now available from the user Ad Center.",
        parse_mode="Markdown"
    )


async def setadreward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    raw = update.message.text.partition(" ")[2].strip()

    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Use:\n`/setadreward 0.0001`",
            parse_mode="Markdown"
        )
        return

    set_setting("ad_reward", value)

    conn = db()
    conn.execute(
        "UPDATE ads SET reward=? WHERE active=1",
        (value,)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Ad reward set to ${value:.4f}"
    )


async def setrefreward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    raw = update.message.text.partition(" ")[2].strip()

    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Use:\n`/setrefreward 0.001`",
            parse_mode="Markdown"
        )
        return

    set_setting("ref_reward", value)

    await update.message.reply_text(
        f"✅ Referral reward set to ${value:.4f} for future qualifying referrals."
    )


async def setminwithdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    raw = update.message.text.partition(" ")[2].strip()

    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Use:\n`/setminwithdraw 0.50`",
            parse_mode="Markdown"
        )
        return

    set_setting("min_withdraw", value)

    await update.message.reply_text(
        f"✅ Minimum withdrawal set to ${value:.2f}"
    )


async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "📖 *Admin Commands — Quick Guide*\n\n"
        "🛠️ `/admin` — open Admin Dashboard\n\n"
        "🎬 `/setadlink URL` — add/replace Monetag link\n"
        "Example:\n"
        "`/setadlink https://your-monetag-link`\n\n"
        "💵 `/setadreward 0.0001` — change ad reward display\n\n"
        "👥 `/setrefreward 0.001` — change referral reward for future referrals\n\n"
        "🔒 `/setminwithdraw 0.50` — change minimum withdrawal\n\n"
        "💰 `/stats` — quick statistics\n\n"
        "📋 `/withdrawals` — show pending withdrawals\n\n"
        "👥 `/users` — show recent users\n\n"
        "The user withdrawal method is fixed as:\n"
        "USD → BNB Smart Chain (BEP20)\n"
        "Minimum: $0.50",
        parse_mode="Markdown"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    conn = db()

    users = conn.execute(
        "SELECT COUNT(*) AS n FROM users"
    ).fetchone()["n"]

    pending = conn.execute(
        "SELECT COUNT(*) AS n FROM withdrawals WHERE status='pending'"
    ).fetchone()["n"]

    paid = conn.execute(
        "SELECT COUNT(*) AS n FROM withdrawals WHERE status='paid'"
    ).fetchone()["n"]

    balance = conn.execute(
        "SELECT COALESCE(SUM(balance),0) AS n FROM users"
    ).fetchone()["n"]

    conn.close()

    await update.message.reply_text(
        "📊 *Bot Statistics*\n\n"
        f"👤 Users: {users}\n"
        f"⏳ Pending withdrawals: {pending}\n"
        f"✅ Paid withdrawals: {paid}\n"
        f"💰 Current user balances: ${float(balance):.4f}",
        parse_mode="Markdown"
    )


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    conn = db()
    rows = conn.execute("""
        SELECT user_id,username,balance,referral_count
        FROM users
        ORDER BY created_at DESC
        LIMIT 30
    """).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No users yet.")
        return

    text = "👥 *Recent Users*\n\n"

    for row in rows:
        username = f"@{row['username']}" if row["username"] else "-"
        text += (
            f"• `{row['user_id']}` {username}\n"
            f"  Balance: ${float(row['balance']):.4f} | Referrals: {row['referral_count']}\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="Markdown"
    )


async def withdrawals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    await send_withdrawals(update)


async def send_withdrawals(target):
    conn = db()
    rows = conn.execute("""
        SELECT * FROM withdrawals
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    if not rows:
        text = "💸 *Pending Withdrawals*\n\nNo pending withdrawal requests."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Home", callback_data="home")]
        ])
    else:
        text = "💸 *Pending Withdrawals*\n\n"

        for row in rows:
            text += (
                f"🧾 *Request #{row['id']}*\n"
                f"👤 User: `{row['user_id']}`\n"
                f"💵 Amount: *${float(row['amount']):.4f}*\n"
                f"🟡 BEP20: `{row['wallet']}`\n"
                f"⏳ Status: *Pending*\n\n"
            )

        keyboard = withdrawal_admin_keyboard(rows)

    if hasattr(target, "callback_query") and target.callback_query:
        await target.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await target.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )


async def mark_withdrawal(query, withdrawal_id, new_status):
    if not is_admin(query.from_user.id):
        return

    conn = db()

    row = conn.execute("""
        SELECT * FROM withdrawals
        WHERE id=? AND status='pending'
    """, (withdrawal_id,)).fetchone()

    if not row:
        conn.close()
        await query.answer(
            "Request not found or already processed.",
            show_alert=True
        )
        return

    if new_status == "rejected":
        conn.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (row["amount"], row["user_id"])
        )

    if new_status == "paid":
        conn.execute("""
            UPDATE withdrawals
            SET status='paid', paid_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (withdrawal_id,))
    else:
        conn.execute("""
            UPDATE withdrawals
            SET status='rejected'
            WHERE id=?
        """, (withdrawal_id,))

    conn.commit()
    conn.close()

    await query.answer(
        f"Request #{withdrawal_id} marked {new_status}."
    )

    await send_withdrawals(
        type("T", (), {"callback_query": query})()
    )


# =========================
# CALLBACK ROUTER
# =========================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("paid:"):
        await query.answer()
        await mark_withdrawal(
            query,
            int(data.split(":")[1]),
            "paid"
        )
        return

    if data.startswith("reject:"):
        await query.answer()
        await mark_withdrawal(
            query,
            int(data.split(":")[1]),
            "rejected"
        )
        return

    await query.answer()

    if data == "home":
        await query.edit_message_text(
            "🌟 *BNB Token Mining*\n\nChoose an option 👇",
            parse_mode="Markdown",
            reply_markup=home_keyboard()
        )

    elif data == "ads":
        await show_ads(query)

    elif data == "balance":
        await show_balance(query)

    elif data == "ref":
        await show_referral(query)

    elif data == "history":
        await show_history(query)

    elif data == "withdraw":
        await show_withdraw(query)

    elif data == "wallet_prompt":
        await wallet_prompt(query)

    elif data == "help":
        await help_page(query)

    elif data == "ad_info":
        await query.edit_message_text(
            "ℹ️ *Ad Reward Information*\n\n"
            "The displayed reward is configured by the administrator.\n\n"
            "⚠️ A SmartLink click is not proof of a completed ad. "
            "For genuine rewarded advertising, use Monetag's supported rewarded Telegram Mini App integration.",
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )

    # Admin pages
    elif data == "admin_stats":
        conn = db()
        users = conn.execute(
            "SELECT COUNT(*) n FROM users"
        ).fetchone()["n"]
        pending = conn.execute(
            "SELECT COUNT(*) n FROM withdrawals WHERE status='pending'"
        ).fetchone()["n"]
        paid = conn.execute(
            "SELECT COUNT(*) n FROM withdrawals WHERE status='paid'"
        ).fetchone()["n"]
        total_balance = conn.execute(
            "SELECT COALESCE(SUM(balance),0) n FROM users"
        ).fetchone()["n"]
        conn.close()

        await query.edit_message_text(
            "📊 *Admin Statistics*\n\n"
            f"👤 Users: {users}\n"
            f"⏳ Pending withdrawals: {pending}\n"
            f"✅ Paid withdrawals: {paid}\n"
            f"💰 User balances: ${float(total_balance):.4f}",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_users":
        conn = db()
        rows = conn.execute("""
            SELECT user_id,username,balance,referral_count
            FROM users
            ORDER BY created_at DESC
            LIMIT 20
        """).fetchall()
        conn.close()

        text = "👥 *Recent Users*\n\n"

        if not rows:
            text += "No users yet."
        else:
            for row in rows:
                username = f"@{row['username']}" if row["username"] else "-"
                text += (
                    f"• `{row['user_id']}` {username}\n"
                    f"  ${float(row['balance']):.4f} | Ref: {row['referral_count']}\n"
                )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_ads":
        conn = db()
        ad = conn.execute("""
            SELECT * FROM ads
            WHERE active=1
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        conn.close()

        if ad:
            link_status = "Configured ✅"
        else:
            link_status = "Not configured ❌"

        await query.edit_message_text(
            "🎬 *Ad Settings*\n\n"
            f"🔗 Monetag link: *{link_status}*\n"
            f"💵 Ad reward: *${ad_reward():.4f}*\n\n"
            "To add/replace your ad link, send:\n"
            "`/setadlink https://YOUR-MONETAG-LINK`\n\n"
            "To change reward:\n"
            "`/setadreward 0.0001`",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_withdrawals":
        await send_withdrawals(
            type("T", (), {"callback_query": query})()
        )

    elif data == "admin_commands":
        await query.edit_message_text(
            "📖 *Admin Commands*\n\n"
            "🛠️ `/admin` — dashboard\n\n"
            "🎬 `/setadlink URL` — add/replace Monetag link\n"
            "Example:\n"
            "`/setadlink https://example.com`\n\n"
            "💵 `/setadreward 0.0001` — ad reward\n\n"
            "👥 `/setrefreward 0.001` — referral reward for future referrals\n\n"
            "🔒 `/setminwithdraw 0.50` — minimum withdrawal\n\n"
            "📊 `/stats` — statistics\n"
            "👥 `/users` — recent users\n"
            "💸 `/withdrawals` — pending withdrawals\n\n"
            "💳 User payment method is fixed:\n"
            "*USD → BNB Smart Chain (BEP20)*",
            parse_mode="Markdown",
            reply_markup=admin_keyboard()
        )


# =========================
# RENDER HEALTH SERVER
# =========================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"BNB Token Mining bot is running.")

    def log_message(self, *args):
        pass


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


# =========================
# MAIN
# =========================
def main():
    db().close()

    threading.Thread(
        target=start_health_server,
        daemon=True
    ).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))

    # Admin configuration
    app.add_handler(CommandHandler("setadlink", setadlink))
    app.add_handler(CommandHandler("setadreward", setadreward))
    app.add_handler(CommandHandler("setrefreward", setrefreward))
    app.add_handler(CommandHandler("setminwithdraw", setminwithdraw))
    app.add_handler(CommandHandler("admincommands", admin_commands))

    # Admin information
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("withdrawals", withdrawals_command))

    # User wallet submission
    app.add_handler(CommandHandler("wallet", wallet_command))

    app.add_handler(
        CallbackQueryHandler(callbacks)
    )

    print("BNB Token Mining bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
