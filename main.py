import asyncio
import logging
import logging.handlers
from telethon import TelegramClient
from telethon.sessions import StringSession
import config
import storage
from handlers import incoming, commands

_KEEPALIVE_INTERVAL = 120  # seconds between channel pings


def _setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            "userbot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        ),
    ]
    logging.basicConfig(level=logging.DEBUG, format=fmt, handlers=handlers)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


async def main() -> None:
    _setup_logging()
    log = logging.getLogger(__name__)

    await storage.init_db()
    log.info("База данных инициализирована: %s", config.DB_PATH)

    client = TelegramClient(
        StringSession(config.SESSION_STRING),
        config.API_ID,
        config.API_HASH,
        sequential_updates=True,
    )

    incoming.register(client)
    commands.register(client)

    async with client:
        me = await client.get_me()
        log.info("Авторизован как: %s (id=%d)", me.username or me.first_name, me.id)

        log.info("Синхронизация диалогов…")
        count = 0
        async for _ in client.iter_dialogs():
            count += 1
        log.info("Синхронизировано диалогов: %d", count)

        log.info(
            "Управление: отправляйте команды с префиксом '.' в Saved Messages. "
            "Начните с .help"
        )

        asyncio.create_task(_keepalive(client, log))
        await client.run_until_disconnected()


async def _keepalive(client: TelegramClient, log: logging.Logger) -> None:
    """
    Пингует мониторируемые каналы, чтобы Telegram считал сессию активной и
    слал push-обновления без задержки. Простой get_me() недостаточен — нужно
    трогать сами каналы.
    """
    while True:
        await asyncio.sleep(_KEEPALIVE_INTERVAL)
        try:
            pipelines = await storage.get_all_pipelines()
            source_ids = {p.source_id for p in pipelines}
            for source_id in source_ids:
                try:
                    await client.get_messages(source_id, limit=1)
                except Exception:
                    log.debug("keepalive: не удалось пинговать канал %d", source_id)
            log.debug("keepalive: пингованы каналы %s", source_ids)
        except Exception:
            log.warning("keepalive: ошибка", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
