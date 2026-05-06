import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN", "")

if not token:
    print("TELEGRAM_BOT_TOKEN не найден в .env")
    exit()

print(f"Токен: {token[:10]}...{token[-5:]}")
print("\nПоследние сообщения, полученные ботом:\n")

r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
data = r.json()

if not data.get("ok"):
    print(f"Ошибка API: {data}")
    exit()

updates = data.get("result", [])
if not updates:
    print("Бот НЕ получил ни одного сообщения!")
    print("Открой Telegram → найди своего бота → отправь /start")
    print("Затем перезапусти этот скрипт")
    exit()

for u in updates:
    msg = u.get("message", {})
    chat = msg.get("chat", {})
    print(f"  От: {chat.get('first_name', '')} {chat.get('last_name', '')} (@{chat.get('username', 'N/A')})")
    print(f"  chat_id = {chat.get('id')}")
    print(f"  Текст: {msg.get('text', '')}")
    print()

print("Скопируй chat_id в .env → TELEGRAM_CHAT_ID=<число>")
