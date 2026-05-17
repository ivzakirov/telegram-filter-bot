"""
One-time script to generate a SESSION_STRING.

Usage:
    python gen_session.py

Reads API_ID and API_HASH from .env if present, otherwise prompts for them.
Prints the session string — copy it into .env as SESSION_STRING=...
"""
import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()


async def main() -> None:
    print("=== Telegram userbot session string generator ===\n")

    api_id_env = os.getenv("API_ID", "").strip()
    api_hash_env = os.getenv("API_HASH", "").strip()

    if api_id_env and api_hash_env:
        api_id = int(api_id_env)
        api_hash = api_hash_env
        print(f"Using API_ID and API_HASH from .env\n")
    else:
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
