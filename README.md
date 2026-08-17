# BNB Token Mining Telegram Bot

A clean MVP Telegram task/points bot for `@bnbtokenminingbot`.

## Features
- Main menu with Tasks, Balance, Referral, Withdraw, Help
- Back/Home navigation on every screen
- Admin panel
- Add/deactivate/list tasks
- One-time task claim protection
- SQLite database
- Render health server
- Admin ID is configured in `bot.py`

## Render
Build command:
`pip install -r requirements.txt`

Start command:
`python bot.py`

Environment variable:
`BOT_TOKEN` = your BotFather token

Never put the BotFather token in GitHub.

## Task format
`/addtask Title | reward | https://example.com`

This MVP does not claim external task completion automatically. Real sponsor verification and real payouts must be connected before real money is credited.
