from __future__ import annotations
import asyncio
import logging
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


# Media group (album) accumulation
# grouped_id → list of message IDs
_pending_groups: dict[int, list[int]] = {}
# grouped_id → list of (output_id, source_title, filter_label, client)
_group_destinations: dict[int, list[tuple]] = {}


async def _send_to_output(
    client,
    output_id: int,
    msg_ids: list[int] | int,
    source_id: int,
    source_title: str,
    filter_label: str,
    text_fallback: str = "",
) -> None:
    """Forward message(s) to output_id and send a label. Serialised per output_id."""
    ids = msg_ids if isinstance(msg_ids, list) else [msg_ids]
    is_album = isinstance(msg_ids, list)

    async with _get_lock(output_id):
        forwarded = False
        try:
            await client.forward_messages(output_id, messages=ids, from_peer=source_id)
            forwarded = True
            log.info("Переслано%s: msgs=%s source=%d → output=%d",
                     " (альбом)" if is_album else "", ids, source_id, output_id)
        except ChatForwardsRestrictedError:
            log.warning("Пересылка запрещена в чате %d", source_id)
        except FloodWaitError as e:
            log.warning("FloodWait %ds при пересылке", e.seconds)
            await asyncio.sleep(e.seconds)
            await client.forward_messages(output_id, messages=ids, from_peer=source_id)
            forwarded = True

        prefix = "📌" if forwarded else "⚠️ (пересылка запрещена)"
        label_msg = f"{prefix} {source_title} — {filter_label}"
        if not forwarded and text_fallback:
            label_msg += f"\n\n{text_fallback[:200]}"
        await client.send_message(output_id, label_msg)


async def _flush_group(grouped_id: int) -> None:
    """Wait 1 s for all album photos to arrive, then forward to each matched pipeline."""
    await asyncio.sleep(1.0)
    msg_ids = _pending_groups.pop(grouped_id, [])
    destinations = _group_destinations.pop(grouped_id, [])
    if not msg_ids or not destinations:
        return
    for output_id, source_id, source_title, filter_label, client in destinations:
        try:
            await _send_to_output(client, output_id, msg_ids, source_id, source_title, filter_label)
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
            author = getattr(sender, "username", None) or str(getattr(sender, "id", ""))
        else:
            author = ""

        results = await service.get_matching_pipelines(source_id, text, author)
        log.debug("Пайплайны: source=%s matched=%d/%d", source_id, len(results), len(pipelines))
        if not results:
            return

        # Grouped message (album): accumulate IDs, flush after 1s
        grouped_id = event.message.grouped_id
        if grouped_id:
            _pending_groups.setdefault(grouped_id, []).append(event.message.id)
            if grouped_id not in _group_destinations:
                # Destinations determined by first photo; all photos in group share same filters
                destinations = []
                for pipeline, matched in results:
                    if matched == ["*"]:
                        filter_label = "проходит все"
                    else:
                        filter_label = f"фильтры: {', '.join(matched)}"
                    destinations.append((
                        pipeline.output_id, source_id,
                        pipeline.source_title, filter_label, event.client,
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
                    source_id, pipeline.source_title, filter_label, text,
                )
            except Exception:
                log.exception("Ошибка пересылки: pipeline=%s msg=%d",
                              pipeline.name, event.message.id)

    except Exception:
        log.exception("Ошибка в incoming handler: chat=%d", event.chat_id)


def register(client) -> None:
    client.add_event_handler(_handle, events.NewMessage())
