# BNB Token Mining — COMPLETE FINAL SETUP

এই package-টি একসাথে GitHub + Render-এর জন্য তৈরি করা হয়েছে।

## 1. Files

এই ZIP-এর ভিতরে মাত্র ৩টি file:

- `bot.py`
- `requirements.txt`
- `README.md`

GitHub repository-তে এই তিনটি file একই folder/root-এ রাখবে।

## 2. Render

Existing Render service থাকলে নতুন service বানানোর দরকার নেই।

### Build Command
```text
pip install -r requirements.txt
```

### Start Command
```text
python bot.py
```

### Environment Variable

Render → Environment → Add Environment Variable:

```text
Key: BOT_TOKEN
Value: তোমার BotFather token
```

Bot token কখনো GitHub-এ লিখবে না।

## 3. Admin

Admin ID code-এ সেট করা:

```text
5932054746
```

শুধু এই Telegram account `/admin` ব্যবহার করতে পারবে।

## 4. Deploy করার পর প্রথম কাজ

Admin account দিয়ে bot-এ:

```text
/admin
```

দাও।

Admin Dashboard আসবে।

## 5. Monetag Ad Link বসানো

Monetag থেকে তোমার SmartLink/Direct Link কপি করো।

তারপর Admin account দিয়ে:

```text
/setadlink https://YOUR-MONETAG-LINK
```

উদাহরণ:

```text
/setadlink https://example.com/your-monetag-link
```

তারপর:

```text
/admin
```

→ `🎬 Ad Settings`

এখানে দেখাবে:

```text
Monetag link: Configured
```

User-এর:

```text
🎬 Watch Ads & Earn
```

section-এ link দেখা যাবে।

## 6. Ad Reward

Default:

```text
$0.0001
```

চাইলে Admin:

```text
/setadreward 0.0001
```

দিয়ে পরিবর্তন করতে পারবে।

IMPORTANT:
SmartLink click-কে code নিজে থেকে verified ad completion ধরে reward credit করে না।
Verified rewarded earning-এর জন্য Monetag-এর supported rewarded Telegram Mini App integration লাগবে।

## 7. Referral

Default referral reward:

```text
$0.001
```

Admin change করতে:

```text
/setrefreward 0.001
```

একজন নতুন qualifying user referral link দিয়ে প্রথমবার join করলে referrer-এর balance-এ reward যোগ হয়।

## 8. Withdrawal

User-এর জন্য একটাই payment option:

```text
USD
```

Network:

```text
BNB Smart Chain (BEP20)
```

Minimum:

```text
$0.50
```

User:

1. `💸 Withdraw`
2. Balance $0.50 বা তার বেশি হলে `📤 Enter Wallet`
3. Wallet address পাঠাবে:

```text
/wallet 0xYOUR_BEP20_ADDRESS
```

Address valid হলে request তৈরি হবে।

User-এর balance থেকে requested amount hold করে নেওয়া হবে এবং request `Pending` হবে।

## 9. Admin Withdrawal

Admin:

```text
/withdrawals
```

দিলে pending requests দেখাবে।

প্রতিটি request-এ:

```text
✅ Paid
❌ Reject
```

### Paid

তুমি নিজে wallet-এ payment করার পর `Paid` চাপবে।

### Reject

যদি payment না করো/reject করো, requested amount user-এর balance-এ ফেরত যাবে।

## 10. Statistics

Admin:

```text
/stats
```

দিলে users, pending withdrawals, paid withdrawals এবং current balances দেখা যাবে।

## 11. Recent Users

```text
/users
```

## 12. Admin Dashboard

```text
/admin
```

এখান থেকে:

- Statistics
- Users
- Ad Settings
- Pending Withdrawals
- Admin Commands

দেখা যাবে।

## 13. Admin Command Quick List

```text
/admin
/setadlink URL
/setadreward 0.0001
/setrefreward 0.001
/setminwithdraw 0.50
/stats
/users
/withdrawals
/admincommands
```

## 14. Telegram Bot Conflict

যদি দেখো:

```text
telegram.error.Conflict:
terminated by other getUpdates request
```

তাহলে একই bot token দিয়ে দুইটা polling instance চলছে।

একই bot-এর পুরোনো Render service/duplicate service বন্ধ করো এবং শুধু একটি instance চালু রাখো।

## 15. Security

- BotFather token GitHub-এ দেবে না।
- Admin ID ছাড়া Admin commands কাজ করবে না।
- User wallet শুধু BEP20 format-এ নেওয়া হয়।
- Withdrawal manual payment system।
- SmartLink click-কে verified ad completion হিসেবে automatically credit করা হয় না।
