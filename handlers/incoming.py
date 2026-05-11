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

# Media group (album) accumulation: grouped_id → list of message IDs
_pending_groups: dict[int, list[int]] = {}
_group_meta: dict[int, tuple] = {}  # grouped_id → (client, chat_id, chat_title, filter_label)


async def _flush_group(grouped_id: int) -> None:
    """Wait for the rest of an album to arrive, then forward all photos at once."""
    await asyncio.sleep(1.0)
    msg_ids = _pending_groups.pop(grouped_id, [])
    meta = _group_meta.pop(grouped_id, None)
    if not msg_ids or not meta:
        return
    client, chat_id, chat_title, filter_label = meta
    try:
        async with _output_lock:
            forwarded = False
            try:
                await client.forward_messages(OUTPUT_CHAT, messages=msg_ids, from_peer=chat_id)
                forwarded = True
                log.info("Переслано (альбом %d фото): chat=%d → OUTPUT_CHAT", len(msg_ids), chat_id)
            except ChatForwardsRestrictedError:
                log.warning("Пересылка запрещена в чате %d — отправляю только уведомление", chat_id)
            except FloodWaitError as e:
                log.warning("FloodWait %ds при пересылке альбома", e.seconds)
                await asyncio.sleep(e.seconds)
                await client.forward_messages(OUTPUT_CHAT, messages=msg_ids, from_peer=chat_id)
                forwarded = True

            prefix = "📌" if forwarded else "⚠️ (пересылка запрещена)"
            await client.send_message(OUTPUT_CHAT, f"{prefix} {chat_title} — {filter_label}")
    except Exception:
        log.exception("Ошибка при пересылке альбома: chat=%d grouped_id=%d", chat_id, grouped_id)


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

        sender = await event.get_sender()
        if sender:
            author = getattr(sender, "username", None) or str(getattr(sender, "id", ""))
        else:
            author = ""

        matched = await service.get_matching_filters(chat_id, text, author)
        log.debug("Фильтрация: chat=%s author=%s matched=%s", chat_id, author, matched)
        if not matched:
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", None) or str(chat_id)

        if matched == ["*"]:
            filter_label = "проходит все"
        else:
            filter_label = f"фильтры: {', '.join(matched)}"

        log.info("Совпадение: chat=%d msg=%d %s", chat_id, event.message.id, filter_label)

        # Media group (album): accumulate all photos, flush after 1s
        grouped_id = event.message.grouped_id
        if grouped_id:
            _pending_groups.setdefault(grouped_id, []).append(event.message.id)
            if grouped_id not in _group_meta:
                _group_meta[grouped_id] = (event.client, chat_id, chat_title, filter_label)
                asyncio.create_task(_flush_group(grouped_id))
            return

        # Single message
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
