"""
Одноразовый скрипт для генерации SESSION_STRING.

Запуск:
    python gen_session.py

Скрипт запросит API_ID, API_HASH, номер телефона и код подтверждения,
затем напечатает строку сессии. Скопируйте её в .env как SESSION_STRING=...
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    print("=== Генерация session string для Telegram userbot ===\n")
    api_id = int(input("API_ID (число с my.telegram.org): ").strip())
    api_hash = input("API_HASH (строка с my.telegram.org): ").strip()

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()

    print("\n" + "=" * 60)
    print("SESSION_STRING (скопируйте в .env):")
    print(session_string)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
