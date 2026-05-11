from __future__ import annotations
import asyncio
import logging
from telethon import events
from telethon.errors import FloodWaitError, ChatForwardsRestrictedError
import service
import storage
from config import OUTPUT_CHAT

log = logging.getLogger(__name__)

# Serialise all OUTPUT_CHAT writes to avoid Telegram rate-limit errors on burst catch-up
_output_lock = asyncio.Lock()


async def _handle(event: events.NewMessage.Event) -> None:
    try:
        if event.out:
            return

        chat_id = event.chat_id
        monitored = await storage.is_monitored(chat_id)
        log.debug("Входящее: chat=%s monitored=%s", chat_id, monitored)
        if not monitored:
            return

        text: str = event.raw_text or ""

        matched = await service.get_matching_filters(chat_id, text)
        log.debug("Фильтрация: chat=%s matched=%s", chat_id, matched)
        if not matched:
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", None) or str(chat_id)

        if matched == ["*"]:
            filter_label = "проходит все"
        else:
            filter_label = f"фильтры: {', '.join(matched)}"

        log.info("Совпадение: chat=%d msg=%d %s", chat_id, event.message.id, filter_label)

        client = event.client
        forwarded = False
        async with _output_lock:
            try:
                await client.forward_messages(OUTPUT_CHAT, messages=event.message.id, from_peer=chat_id)
                forwarded = True
                log.info("Переслано: msg=%d chat=%d → OUTPUT_CHAT", event.message.id, chat_id)
            except ChatForwardsRestrictedError:
                log.warning("Пересылка запрещена в чате %d — отправляю только уведомление", chat_id)
            except FloodWaitError as e:
                log.warning("FloodWait %ds при пересылке", e.seconds)
                await asyncio.sleep(e.seconds)
                await client.forward_messages(OUTPUT_CHAT, messages=event.message.id, from_peer=chat_id)
                forwarded = True

            prefix = "📌" if forwarded else "⚠️ (пересылка запрещена)"
            text_preview = text[:200] if not forwarded else ""
            label_msg = f"{prefix} {chat_title} — {filter_label}"
            if text_preview:
                label_msg += f"\n\n{text_preview}"
            await client.send_message(OUTPUT_CHAT, label_msg)
    except Exception:
        log.exception("Ошибка в incoming handler: chat=%d", event.chat_id)


def register(client) -> None:
    client.add_event_handler(_handle, events.NewMessage())
