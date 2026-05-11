from __future__ import annotations
import logging
from typing import Optional
from telethon.utils import get_peer_id
import expr_parser
import storage
from storage import Pipeline, Filter

log = logging.getLogger(__name__)


def _eval_filters(filters: list[Filter], text: str, author: str) -> list[str]:
    """
    Core allow/block logic for a single pipeline's filter set.

    Returns:
      []    — blocked or no allow-filter matched
      ["*"] — pass-all (no allow-filters, no block triggered)
      [names...] — matched allow-filter names
    """
    allow_filters = [f for f in filters if f.type == "allow"]
    block_filters = [f for f in filters if f.type == "block"]

    for f in block_filters:
        try:
            if expr_parser.evaluate(expr_parser.get_ast(f.id, f.expression), text, author):
                log.debug("Blocked by filter '%s' (pipeline %d)", f.name, f.pipeline_id)
                return []
        except Exception:
            log.warning("Ошибка в block-фильтре '%s'", f.name, exc_info=True)

    if allow_filters:
        matched = []
        for f in allow_filters:
            try:
                if expr_parser.evaluate(expr_parser.get_ast(f.id, f.expression), text, author):
                    matched.append(f.name)
            except Exception:
                log.warning("Ошибка в allow-фильтре '%s'", f.name, exc_info=True)
        return matched

    return ["*"]  # pass-all mode


async def get_matching_pipelines(
    source_id: int, text: str, author: str = ""
) -> list[tuple[Pipeline, list[str]]]:
    """
    For each pipeline listening on source_id, evaluate its filters.
    Returns list of (pipeline, matched_names) for pipelines that should forward.
    """
    pipelines = await storage.get_pipelines_for_source(source_id)
    results = []
    for pipeline in pipelines:
        filters = await storage.get_filters_for_pipeline(pipeline.id)
        matched = _eval_filters(filters, text, author)
        if matched:
            results.append((pipeline, matched))
    return results


async def add_pipeline(
    client,
    name: str,
    source_identifier: str,
    output_identifier: str,
) -> Pipeline:
    from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError

    # Resolve source: must be in session cache (bot must be a member)
    try:
        entity = await client.get_entity(source_identifier)
    except (ValueError, UsernameNotOccupiedError, UsernameInvalidError, TypeError) as e:
        raise ValueError(f"Источник не найден: {source_identifier}") from e
    source_id = get_peer_id(entity)
    source_title = getattr(entity, "title", None) or getattr(entity, "first_name", str(source_id))
    source_username = getattr(entity, "username", None)

    # Resolve output: accept raw integer ID directly (avoids get_entity cache miss
    # for chats the bot hasn't seen yet); @username is also supported
    try:
        output_id = int(output_identifier)
    except ValueError:
        try:
            out_entity = await client.get_entity(output_identifier)
            output_id = get_peer_id(out_entity)
        except (ValueError, UsernameNotOccupiedError, UsernameInvalidError, TypeError) as e:
            raise ValueError(f"Выход не найден: {output_identifier}") from e

    existing = await storage.get_pipeline_by_name(name)
    if existing:
        raise ValueError(f"Пайплайн с именем '{name}' уже существует")

    pipeline = await storage.save_pipeline(name, source_id, source_title, source_username, output_id)
    log.info("Пайплайн создан: name=%s source=%d output=%d", name, source_id, output_id)
    return pipeline


async def remove_pipeline(name: str) -> bool:
    result = await storage.delete_pipeline(name)
    if result:
        log.info("Пайплайн удалён: name=%s", name)
    return result


async def add_filter(
    pipeline_id: int,
    name: str,
    expression: str,
    filter_type: str = "allow",
) -> None:
    if filter_type not in ("allow", "block"):
        raise ValueError(f"Неизвестный тип фильтра: {filter_type!r}. Используйте 'allow' или 'block'")
    expr_parser.parse(expression)  # raises SyntaxError if invalid
    await storage.save_filter(pipeline_id, name, expression, filter_type)
    log.info("Фильтр добавлен: pipeline_id=%d name=%s type=%s expr=%r",
             pipeline_id, name, filter_type, expression)


async def remove_filter(pipeline_id: int, name: str) -> bool:
    result = await storage.delete_filter(pipeline_id, name)
    if result:
        log.info("Фильтр удалён: pipeline_id=%d name=%s", pipeline_id, name)
    return result
