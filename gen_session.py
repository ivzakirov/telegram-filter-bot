"""
Одноразовый скрипт для генерации SESSION_STRING.

Запуск:
    python gen_session.py

Скрипт запросит API_ID, API_HASH, номер телефона и код подтверждения,
затем напечатает строку сессии. Скопируйте её в .env как SESSION_STRING=...
"""
import asyncio
# Python 3.10+ не создаёт event loop автоматически; Pyrogram требует его до импорта.
asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client


async def main() -> None:
    print("=== Генерация session string для Telegram userbot ===\n")
    api_id = int(input("API_ID (число с my.telegram.org): ").strip())
    api_hash = input("API_HASH (строка с my.telegram.org): ").strip()

    # Client создаёт файл gen_session.session при первом входе.
    async with Client(name="gen_session", api_id=api_id, api_hash=api_hash) as client:
        session_string = await client.export_session_string()

    print("\n" + "=" * 60)
    print("SESSION_STRING (скопируйте в .env):")
    print(session_string)
    print("=" * 60)
    print("\nФайл gen_session.session можно удалить — он больше не нужен.")


if __name__ == "__main__":
    asyncio.run(main())
