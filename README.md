# BNB Token Mining — ALL IN ONE FINAL

## Render
Build:
`pip install -r requirements.txt`

Start:
`python bot.py`

Environment:
`BOT_TOKEN = your BotFather token`

Admin ID:
`5932054746`

## Telegram command menu
The bot automatically registers the normal user commands and a separate admin command menu for the admin chat.

### User
/start
/balance
/referral
/withdraw
/history
/help

### Admin
/admin
/setadlink URL
/setadreward 0.0001
/setrefreward 0.001
/setminwithdraw 0.50
/stats
/users
/withdrawals
/admincommands

## Add Monetag
After deploy, open the bot with the admin account and use:

`/admin`

or directly:

`/setadlink https://YOUR-MONETAG-LINK`

The Admin Dashboard also has "Ad Settings".

## Default rewards
Ad display reward: $0.0001
Referral reward: $0.001
Minimum withdrawal: $0.50

## Withdrawal
Only:
USD -> BNB Smart Chain (BEP20)

User flow:
Withdraw -> Enter Wallet -> send BEP20 address as a normal message.

The bot accepts a 42-character hexadecimal address beginning with 0x.
The request becomes Pending and the user's balance is reserved.
Admin manually pays and presses Paid.
If rejected, the amount is returned to the user.

## Important Monetag note
A SmartLink click alone is not treated as verified completion and is not automatically credited.
For genuine rewarded ad verification, use Monetag's supported rewarded Telegram Mini App integration.

## Conflict error
If Telegram says:
`telegram.error.Conflict: terminated by other getUpdates request`
only one instance of this bot token may run polling. Stop any duplicate Render service/process and keep one instance.
