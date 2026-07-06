"""
telegram_hello.py - Step 1: prove Python can reach your Telegram.

What it does:
1. Finds your chat ID automatically (from you pressing Start on the bot)
2. Sends you a hello message
3. Prints your chat ID so we can use it in the alert script later

Run:
    pip install requests
    python telegram_hello.py

It will ask for your bot token. Paste it when prompted.
"""

import requests

BOT_TOKEN = input("Paste your bot token from BotFather: ").strip()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Step 1: find your chat ID from recent messages to the bot
print("\nLooking for your chat ID...")
resp = requests.get(f"{API}/getUpdates").json()

if not resp.get("ok"):
    print("Token problem:", resp.get("description", "unknown error"))
    print("Double-check you copied the full token from BotFather.")
    raise SystemExit(1)

updates = resp.get("result", [])
chat_id = None
for update in updates:
    msg = update.get("message") or update.get("my_chat_member") or {}
    chat = msg.get("chat", {})
    if chat.get("id"):
        chat_id = chat["id"]
        name = chat.get("first_name", "you")

if not chat_id:
    print("No chat found yet. Open Telegram, go to your bot,")
    print("send it any message (even 'hi'), then run this script again.")
    raise SystemExit(1)

print(f"Found chat ID: {chat_id}")

# Step 2: send the hello
send = requests.get(
    f"{API}/sendMessage",
    params={
        "chat_id": chat_id,
        "text": "Hello! Your alert pipe is live. \n\nPython -> Telegram: working. 🎉",
    },
).json()

if send.get("ok"):
    print("\nMessage sent! Check your Telegram.")
    print(f"\nSAVE THIS for the next step -> your chat ID is: {chat_id}")
else:
    print("Send failed:", send.get("description"))
