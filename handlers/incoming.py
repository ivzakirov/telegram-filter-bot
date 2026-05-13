from __future__ import annotations
import asyncio
import logging
from typing import Optional
from telethon import events
from telethon.errors import FloodWaitError, ChatForwardsRestrictedError
import service
import storage

log = logging.getLogger(__name__)

# Per-output-chat locks: serialise writes to each output independently
_output_locks: dict[int, asyncio.Lock] = {}


def _get_lock(output_id: int) -> asyncio.Lock:
    if output_id not in _output_locks:
        _output_locks[output_id] = asyncio.Lock()
    return _output_locks[output_id]


# Service message batching: suppress repetitive labels
_BATCH_SIZE = 20
# pipeline_id → (last_filter_label, count_since_last_service_msg)
_pipeline_batch: dict[int, tuple[str, int]] = {}


def _should_send_label(pipeline_id: int, filter_label: str) -> bool:
    state = _pipeline_batch.get(pipeline_id)
    if state is None:
        _pipeline_batch[pipeline_id] = (filter_label, 1)
        return True
    last_label, count = state
    if last_label != filter_label:
        _pipeline_batch[pipeline_id] = (filter_label, 1)
        return True
    if count >= _BATCH_SIZE:
        _pipeline_batch[pipeline_id] = (filter_label, 1)
        return True
    _pipeline_batch[pipeline_id] = (filter_label, count + 1)
    return False


# Reply chain tracking: source msg IDs → output msg IDs per pipeline
_msg_id_map: dict[int, dict[int, int]] = {}
_MSG_MAP_MAXSIZE = 500


def _store_msg_mapping(pipeline_id: int, source_ids: list[int], forwarded_msgs) -> None:
    mapping = _msg_id_map.setdefault(pipeline_id, {})
    for src_id, out_msg in zip(source_ids, forwarded_msgs):
        mapping[src_id] = out_msg.id
    if len(mapping) > _MSG_MAP_MAXSIZE:
        excess = len(mapping) - _MSG_MAP_MAXSIZE
        for key in list(mapping.keys())[:excess]:
            del mapping[key]


async def _copy_as_reply(client, output_id: int, msg, reply_to_output_id: int, sender_name: str):
    """Send msg content as a reply to reply_to_output_id (copy-forward, preserves reply chain)."""
    prefix = f"**{sender_name}:** " if sender_name else ""
    if msg.media:
        caption = prefix + (msg.message or "")
        return await client.send_file(
            output_id, msg.media,
            caption=caption or None,
            reply_to=reply_to_output_id,
            parse_mode="md",
        )
    else:
        return await client.send_message(
            output_id,
            prefix + (msg.message or ""),
            reply_to=reply_to_output_id,
            parse_mode="md",
        )


# Media group (album) accumulation
# grouped_id → list of message IDs
_pending_groups: dict[int, list[int]] = {}
# grouped_id → list of (output_id, source_id, source_title, filter_label, pipeline_id, client)
_group_destinations: dict[int, list[tuple]] = {}


async def _send_to_output(
    client,
    output_id: int,
    msg_ids: list[int] | int,
    source_id: int,
    source_title: str,
    filter_label: str,
    pipeline_id: int,
    text_fallback: str = "",
    message=None,
    reply_to_source_id: Optional[int] = None,
    sender_name: str = "",
) -> None:
    """Forward message(s) to output_id and send a label. Serialised per output_id."""
    ids = msg_ids if isinstance(msg_ids, list) else [msg_ids]
    is_album = isinstance(msg_ids, list)

    async with _get_lock(output_id):
        output_reply_id: Optional[int] = None
        if reply_to_source_id is not None:
            output_reply_id = _msg_id_map.get(pipeline_id, {}).get(reply_to_source_id)

        forwarded = False

        # Copy-forward as reply when the replied-to message is already in output
        if output_reply_id and message and not is_album:
            try:
                out_msg = await _copy_as_reply(client, output_id, message, output_reply_id, sender_name)
                _store_msg_mapping(pipeline_id, [message.id], [out_msg])
                forwarded = True
                log.info("Скопировано как ответ: msg=%d → reply_to=%d output=%d",
                         message.id, output_reply_id, output_id)
            except Exception:
                log.warning("Ошибка copy-as-reply, откат к forward", exc_info=True)

        if not forwarded:
            try:
                result = await client.forward_messages(output_id, messages=ids, from_peer=source_id)
                result_list = result if isinstance(result, list) else [result]
                _store_msg_mapping(pipeline_id, ids, result_list)
                forwarded = True
                log.info("Переслано%s: msgs=%s source=%d → output=%d",
                         " (альбом)" if is_album else "", ids, source_id, output_id)
            except ChatForwardsRestrictedError:
                log.warning("Пересылка запрещена в чате %d", source_id)
            except FloodWaitError as e:
                log.warning("FloodWait %ds при пересылке", e.seconds)
                await asyncio.sleep(e.seconds)
                result = await client.forward_messages(output_id, messages=ids, from_peer=source_id)
                result_list = result if isinstance(result, list) else [result]
                _store_msg_mapping(pipeline_id, ids, result_list)
                forwarded = True

        if not forwarded:
            label_msg = f"⚠️ (пересылка запрещена) {source_title} — {filter_label}"
            if text_fallback:
                label_msg += f"\n\n{text_fallback[:200]}"
            await client.send_message(output_id, label_msg)
        elif _should_send_label(pipeline_id, filter_label):
            await client.send_message(output_id, f"📌 {source_title} — {filter_label}")


async def _flush_group(grouped_id: int) -> None:
    """Wait 1 s for all album photos to arrive, then forward to each matched pipeline."""
    await asyncio.sleep(1.0)
    msg_ids = _pending_groups.pop(grouped_id, [])
    destinations = _group_destinations.pop(grouped_id, [])
    if not msg_ids or not destinations:
        return
    for output_id, source_id, source_title, filter_label, pipeline_id, client in destinations:
        try:
            await _send_to_output(client, output_id, msg_ids, source_id, source_title, filter_label, pipeline_id)
        except Exception:
            log.exception("Ошибка при пересылке альбома grouped_id=%d output=%d", grouped_id, output_id)


async def _handle(event: events.NewMessage.Event) -> None:
    try:
        if event.out:
            return

        source_id = event.chat_id
        pipelines = await storage.get_pipelines_for_source(source_id)
        if not pipelines:
            log.debug("Нет пайплайнов для chat=%s", source_id)
            return

        text: str = event.raw_text or ""

        sender = await event.get_sender()
        if sender:
            username = getattr(sender, "username", None)
            first_name = getattr(sender, "first_name", None) or getattr(sender, "title", None)
            author = username or str(getattr(sender, "id", ""))
            sender_name = (f"@{username}" if username else first_name or author)
        else:
            author = ""
            sender_name = ""

        results = await service.get_matching_pipelines(source_id, text, author)
        log.debug("Пайплайны: source=%s matched=%d/%d", source_id, len(results), len(pipelines))
        if not results:
            return

        reply_to_source_id: Optional[int] = None
        if event.message.reply_to:
            reply_to_source_id = event.message.reply_to.reply_to_msg_id

        # Grouped message (album): accumulate IDs, flush after 1s
        grouped_id = event.message.grouped_id
        if grouped_id:
            _pending_groups.setdefault(grouped_id, []).append(event.message.id)
            if grouped_id not in _group_destinations:
                destinations = []
                for pipeline, matched in results:
                    if matched == ["*"]:
                        filter_label = "проходит все"
                    else:
                        filter_label = f"фильтры: {', '.join(matched)}"
                    destinations.append((
                        pipeline.output_id, source_id,
                        pipeline.source_title, filter_label,
                        pipeline.id, event.client,
                    ))
                    log.info("Совпадение (альбом): pipeline=%s msg=%d %s",
                             pipeline.name, event.message.id, filter_label)
                _group_destinations[grouped_id] = destinations
                asyncio.create_task(_flush_group(grouped_id))
            return

        # Single message: forward to each matched pipeline's output
        for pipeline, matched in results:
            if matched == ["*"]:
                filter_label = "проходит все"
            else:
                filter_label = f"фильтры: {', '.join(matched)}"
            log.info("Совпадение: pipeline=%s msg=%d %s",
                     pipeline.name, event.message.id, filter_label)
            try:
                await _send_to_output(
                    event.client, pipeline.output_id, event.message.id,
                    source_id, pipeline.source_title, filter_label,
                    pipeline.id, text,
                    message=event.message,
                    reply_to_source_id=reply_to_source_id,
                    sender_name=sender_name,
                )
            except Exception:
                log.exception("Ошибка пересылки: pipeline=%s msg=%d",
                              pipeline.name, event.message.id)

    except Exception:
        log.exception("Ошибка в incoming handler: chat=%d", event.chat_id)


def register(client) -> None:
    client.add_event_handler(_handle, events.NewMessage())
