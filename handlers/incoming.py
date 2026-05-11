from __future__ import annotations
import asyncio
import logging
from telethon import events
from telethon.errors import FloodWaitError
import service
import storage
from config import OUTPUT_CHAT

log = logging.getLogger(__name__)


async def _handle(event: events.NewMessage.Event) -> None:
    try:
        if event.out:  # не обрабатываем собственные сообщения
            return

        chat_id = event.chat_id
        if not await storage.is_monitored(chat_id):
            return

        text: str = event.raw_text or ""
        if not text.strip():
            return

        matched = await service.get_matching_filters(chat_id, text)
        if not matched:
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", None) or str(chat_id)

        log.info(
            "Совпадение: chat=%d msg=%d filters=[%s]",
            chat_id,
            event.message.id,
            ", ".join(matched),
        )

        client = event.client
        try:
            await client.forward_messages(OUTPUT_CHAT, messages=event.message.id, from_peer=chat_id)
        except FloodWaitError as e:
            log.warning("FloodWait %ds при пересылке", e.seconds)
            await asyncio.sleep(e.seconds)
            await client.forward_messages(OUTPUT_CHAT, messages=event.message.id, from_peer=chat_id)

        await client.send_message(
            OUTPUT_CHAT,
            f"📌 {chat_title} — фильтры: {', '.join(matched)}",
        )
    except Exception:
        log.exception("Ошибка в incoming handler: chat=%d", event.chat_id)


def register(client) -> None:
    client.add_event_handler(_handle, events.NewMessage())
