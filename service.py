from __future__ import annotations
import logging
from typing import Optional
from telethon.utils import get_peer_id
import expr_parser
import storage

log = logging.getLogger(__name__)


async def get_matching_filters(chat_id: int, text: str) -> list[str]:
    """
    Decide whether a message should be forwarded and why.

    Returns:
      []    — message is blocked or no allow-filter matched (do not forward)
      ["*"] — no allow-filters defined, message passed through (blocks not triggered)
      [names...] — matched allow-filter names (forward with these labels)

    Logic:
      1. If any block-filter matches → block regardless of allow-filters.
      2. If allow-filters exist → forward only if at least one matches.
      3. If no allow-filters exist → forward everything not blocked ("pass-all" mode).
    """
    filters = await storage.get_filters_for_chat(chat_id)

    allow_filters = [f for f in filters if f.type == "allow"]
    block_filters = [f for f in filters if f.type == "block"]

    # Step 1: check block filters
    for f in block_filters:
        try:
            if expr_parser.evaluate(expr_parser.get_ast(f.id, f.expression), text):
                log.debug("Blocked by filter '%s': chat=%d", f.name, chat_id)
                return []
        except Exception:
            log.warning("Ошибка при вычислении block-фильтра '%s'", f.name, exc_info=True)

    # Step 2: check allow filters
    if allow_filters:
        matched = []
        for f in allow_filters:
            try:
                if expr_parser.evaluate(expr_parser.get_ast(f.id, f.expression), text):
                    matched.append(f.name)
            except Exception:
                log.warning("Ошибка при вычислении allow-фильтра '%s'", f.name, exc_info=True)
        return matched  # empty list → no match → do not forward

    # Step 3: pass-all mode (no allow filters, blocks already checked)
    return ["*"]


async def add_filter(
    name: str,
    expression: str,
    chat_id: Optional[int] = None,
    filter_type: str = "allow",
) -> None:
    if filter_type not in ("allow", "block"):
        raise ValueError(f"Неизвестный тип фильтра: {filter_type!r}. Используйте 'allow' или 'block'")
    expr_parser.parse(expression)  # raises SyntaxError if invalid
    await storage.save_filter(name, expression, chat_id, filter_type)
    log.info(
        "Фильтр добавлен: name=%s type=%s chat_id=%s expr=%r",
        name, filter_type, chat_id, expression,
    )


async def remove_filter(name: str) -> bool:
    result = await storage.delete_filter(name)
    if result:
        log.info("Фильтр удалён: name=%s", name)
    return result


async def add_chat(client, identifier: str) -> storage.MonitoredChat:
    from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError

    try:
        entity = await client.get_entity(identifier)
    except (ValueError, UsernameNotOccupiedError, UsernameInvalidError, TypeError) as e:
        raise ValueError(f"Чат не найден: {identifier}") from e

    chat_id = get_peer_id(entity)
    title = getattr(entity, "title", None) or getattr(entity, "first_name", str(chat_id))
    username = getattr(entity, "username", None)

    await storage.save_chat(chat_id, title, username)
    log.info("Чат добавлен: id=%d title=%r", chat_id, title)
    return storage.MonitoredChat(chat_id, title, username)


async def remove_chat(client, identifier: str) -> bool:
    try:
        entity = await client.get_entity(identifier)
        chat_id = get_peer_id(entity)
    except Exception:
        try:
            chat_id = int(identifier)
        except ValueError:
            raise ValueError(f"Не удалось определить chat_id для: {identifier}")

    result = await storage.delete_chat(chat_id)
    if result:
        log.info("Чат удалён: id=%d", chat_id)
    return result
