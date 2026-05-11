from __future__ import annotations
import logging
from typing import Optional
from telethon.utils import get_peer_id
import expr_parser
import storage

log = logging.getLogger(__name__)


async def get_matching_filters(chat_id: int, text: str) -> list[str]:
    filters = await storage.get_filters_for_chat(chat_id)
    matched: list[str] = []
    for f in filters:
        try:
            ast = expr_parser.get_ast(f.id, f.expression)
            if expr_parser.evaluate(ast, text):
                matched.append(f.name)
        except Exception:
            log.warning("Ошибка при вычислении фильтра '%s'", f.name, exc_info=True)
    return matched


async def add_filter(
    name: str, expression: str, chat_id: Optional[int] = None
) -> None:
    expr_parser.parse(expression)  # raises SyntaxError if invalid
    await storage.save_filter(name, expression, chat_id)
    log.info("Фильтр добавлен: name=%s chat_id=%s expr=%r", name, chat_id, expression)


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
