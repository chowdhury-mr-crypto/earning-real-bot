# Earning Real — Telegram Bot MVP

This is a starter/demo for @earningrealbot.

## What it does
- Registers users
- Shows balance
- Shows sponsored tasks stored in SQLite
- Prevents the same task from being credited twice
- Shows a referral link
- Includes a placeholder withdrawal screen

## Important
This starter does NOT fake earnings and does NOT automatically claim that a user completed an external ad/task. Real task verification and real payouts must be connected to legitimate sponsors/payment providers.

## Run
1. Install Python 3.11+.
2. In this folder run:
   pip install -r requirements.txt
3. Set your BotFather token as an environment variable:
   - Windows PowerShell:
     $env:BOT_TOKEN="YOUR_TOKEN"
   - Linux/macOS:
     export BOT_TOKEN="YOUR_TOKEN"
4. Run:
   python bot.py

NEVER publish your BotFather token or put it into a public GitHub repository.
