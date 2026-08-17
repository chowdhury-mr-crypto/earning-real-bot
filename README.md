# BNB Token Mining — User Friendly Full Setup

## Render
Build command:
`pip install -r requirements.txt`

Start command:
`python bot.py`

Environment variable:
`BOT_TOKEN` = your BotFather token

Admin ID is configured in `bot.py` as `5932054746`.

## Admin setup after deploy
Use these commands from the admin account:

`/setadlink https://YOUR-MONETAG-SMARTLINK`
`/setadreward 0.0001`
`/setrefreward 0.001`
`/setminwithdraw 1`

## Withdrawal
Users can request:
`/withdraw TRX WALLET_ADDRESS 1.00`

Methods:
TRX, USDT-TRC20, BNB, BTC, LTC, USD

The admin can mark pending requests Paid or Rejected from the Admin Dashboard. Rejected requests are returned to the user's balance.

## Important
A SmartLink click is not automatically treated as verified ad completion. For genuine rewarded advertising, use Monetag's supported rewarded Telegram Mini App integration. Manual payout is supported, but real payment is performed by the administrator.
