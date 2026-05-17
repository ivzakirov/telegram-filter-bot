import asyncio
import logging
import logging.handlers
from telethon import TelegramClient
from telethon.sessions import StringSession
import config
import storage
from handlers import incoming, commands

_KEEPALIVE_INTERVAL = 120  # seconds between catchup runs


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
    log.info("Database initialized: %s", config.DB_PATH)

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
        log.info("Authorized as: %s (id=%d)", me.username or me.first_name, me.id)

        log.info("Syncing dialogs…")
        count = 0
        async for _ in client.iter_dialogs():
            count += 1
        log.info("Dialogs synced: %d", count)

        log.info(
            "Management: send commands with '.' prefix to Saved Messages. "
            "Start with .help"
        )

        log.info("Catching up missed messages…")
        await incoming.catchup(client)
        log.info("Catchup complete")

        asyncio.create_task(_keepalive(client, log))
        await client.run_until_disconnected()


async def _keepalive(client: TelegramClient, log: logging.Logger) -> None:
    """
    Periodically runs catchup: fetches missed messages by watermark
    and pings channels to keep the session alive.
    Covers sleep/wake scenarios without restarting the bot.
    """
    while True:
        await asyncio.sleep(_KEEPALIVE_INTERVAL)
        try:
            await incoming.catchup(client)
            log.debug("keepalive: catchup complete")
        except Exception:
            log.warning("keepalive: error", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
