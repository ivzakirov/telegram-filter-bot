import asyncio
# Python 3.10+ не создаёт event loop автоматически; Pyrogram требует его до импорта.
asyncio.set_event_loop(asyncio.new_event_loop())

import logging
import logging.handlers
from pyrogram import Client
import config
import storage
from handlers import incoming, commands


def _setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            "userbot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        ),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)
    logging.getLogger("pyrogram").setLevel(logging.WARNING)


async def main() -> None:
    _setup_logging()
    log = logging.getLogger(__name__)

    await storage.init_db()
    log.info("База данных инициализирована: %s", config.DB_PATH)

    app = Client(
        "userbot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=config.SESSION_STRING,
    )

    incoming.register(app)
    commands.register(app)

    log.info("Userbot запускается…")
    async with app:
        me = await app.get_me()
        log.info("Авторизован как: %s (id=%d)", me.username or me.first_name, me.id)

        # Синхронизируем все диалоги — без этого Telegram не шлёт обновления
        # из части групп и каналов до первого взаимодействия с ними.
        log.info("Синхронизация диалогов…")
        count = 0
        async for _ in app.get_dialogs():
            count += 1
        log.info("Синхронизировано диалогов: %d", count)

        log.info(
            "Управление: отправляйте команды с префиксом '.' в Saved Messages. "
            "Начните с .help"
        )
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
