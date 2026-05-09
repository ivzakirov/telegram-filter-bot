from __future__ import annotations
import asyncio
import logging
from pyrogram import Client
from pyrogram.handlers import MessageHandler
from pyrogram.errors import FloodWait
import service
import storage
from config import OUTPUT_CHAT

log = logging.getLogger(__name__)


async def _handle(client: Client, message) -> None:
    try:
        if not await storage.is_monitored(message.chat.id):
            log.info("Чат не в списке отслеживаемых: chat=%d msg=%d",
                message.chat.id,
                message.id)
            return

        text: str = message.text or message.caption or ""
        if not text.strip():
            log.info("Пустое сообщение: chat=%d msg=%d",
                message.chat.id,
                message.id)
            return

        log.info("Проверка сообщения...: chat=%d msg=%d text=[%s]",
            message.chat.id,
            message.id,
            text)

        matched = await service.get_matching_filters(message.chat.id, text)
        if not matched:
            return

        chat_title = getattr(message.chat, "title", None) or str(message.chat.id)
        log.info(
            "Совпадение: chat=%d msg=%d filters=[%s]",
            message.chat.id,
            message.id,
            ", ".join(matched),
        )

        try:
            await client.forward_messages(OUTPUT_CHAT, message.chat.id, message.id)
        except FloodWait as e:
            log.warning("FloodWait %ds при пересылке", e.value)
            await asyncio.sleep(e.value)
            await client.forward_messages(OUTPUT_CHAT, message.chat.id, message.id)

        await client.send_message(
            OUTPUT_CHAT,
            f"📌 {chat_title} — фильтры: {', '.join(matched)}",
        )
    except Exception:
        log.exception(
            "Ошибка в incoming handler: chat=%d msg=%d",
            message.chat.id,
            message.id,
        )


def register(app: Client) -> None:
    app.add_handler(MessageHandler(_handle), group=1)
