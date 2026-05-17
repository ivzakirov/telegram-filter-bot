"""
One-time script to generate a SESSION_STRING.

Usage:
    python gen_session.py

The script will prompt for API_ID, API_HASH, phone number and confirmation code,
then print the session string. Copy it into .env as SESSION_STRING=...
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    print("=== Telegram userbot session string generator ===\n")
    api_id = int(input("API_ID (from my.telegram.org): ").strip())
    api_hash = input("API_HASH (from my.telegram.org): ").strip()

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()

    print("\n" + "=" * 60)
    print("SESSION_STRING (copy into .env):")
    print(session_string)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
