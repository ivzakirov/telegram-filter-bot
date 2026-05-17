from __future__ import annotations
import logging
from telethon import events
import config
import service
import storage

log = logging.getLogger(__name__)

_HELP = """
**Команды userbot'а** (Saved Messages или личные сообщения от доверенного аккаунта):

`.add_pipeline <name> <source> <output>` — создать пайплайн
`.remove_pipeline <name>` — удалить пайплайн и все его фильтры
`.list_pipelines` — список пайплайнов

`.add_filter <pipeline> [allow|block] <name> <выражение>` — добавить фильтр
`.remove_filter <pipeline> <name>` — удалить фильтр
`.list_filters <pipeline>` — фильтры пайплайна
`.test <pipeline> <имя> <текст> [--from @user]` — проверить фильтр

`.status` — сводка
`.help` — эта справка

**Аргументы:**
• `<source>` и `<output>` — @username или числовой chat_id
• `allow` (по умолчанию) — переслать если совпадает, следующие фильтры не проверяются
• `block` — заблокировать если совпадает, следующие фильтры не проверяются
Фильтры проверяются **по порядку**, первое совпадение определяет результат.
Если ни один не сработал — сообщение проходит (добавьте `block *` последним чтобы блокировать остальное).

**Синтаксис выражений:**
`AND`, `OR`, `NOT`, скобки `()`, фразы в `"кавычках"`
Wildcards: `python*`, `*реклам*`, `байк?`
Regex: `/паттерн/` например `/py(thon|3)/`
Автор: `@username` — совпадает с отправителем

Примеры:
  `.add_pipeline jobs @js_jobs -1001234567890`
  `.add_filter jobs allow python python AND NOT вакансия`
  `.add_filter jobs block spam реклама* OR @spambot`
""".strip()


async def _cmd_add_pipeline(event, args: str) -> None:
    parts = args.split()
    if len(parts) < 3:
        await event.respond(
            "Использование: `.add_pipeline <name> <source> <output>`\n"
            "Пример: `.add_pipeline jobs @js_jobs -1001234567890`"
        )
        return
    name, source_identifier, output_identifier = parts[0], parts[1], parts[2]
    try:
        pipeline = await service.add_pipeline(event.client, name, source_identifier, output_identifier)
        src = f"@{pipeline.source_username}" if pipeline.source_username else str(pipeline.source_id)
        await event.respond(
            f"✅ Пайплайн **{name}** создан\n"
            f"• Источник: {pipeline.source_title} ({src})\n"
            f"• Выход: `{pipeline.output_id}`"
        )
    except Exception as e:
        await event.respond(f"❌ {e}")


async def _cmd_remove_pipeline(event, args: str) -> None:
    name = args.strip()
    if not name:
        await event.respond("Использование: `.remove_pipeline <name>`")
        return
    removed = await service.remove_pipeline(name)
    if removed:
        await event.respond(f"✅ Пайплайн **{name}** удалён")
    else:
        await event.respond(f"⚠️ Пайплайн **{name}** не найден")


async def _cmd_list_pipelines(event, _args: str) -> None:
    pipelines = await storage.get_all_pipelines()
    if not pipelines:
        await event.respond("Пайплайны не созданы. Добавьте: `.add_pipeline <name> <source> <output>`")
        return
    lines = ["**Пайплайны:**"]
    for p in pipelines:
        src = f"@{p.source_username}" if p.source_username else str(p.source_id)
        n_allow, n_block = await storage.count_filters_for_pipeline(p.id)
        filter_info = f"{n_allow}✅ {n_block}🚫" if (n_allow or n_block) else "нет фильтров"
        lines.append(f"• **{p.name}**: {p.source_title} ({src}) → `{p.output_id}` [{filter_info}]")
    await event.respond("\n".join(lines))


async def _cmd_add_filter(event, args: str) -> None:
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await event.respond(
            "Использование: `.add_filter <pipeline> [allow|block] <name> <выражение>`\n"
            "Пример: `.add_filter jobs allow python python AND NOT вакансия`"
        )
        return

    pipeline_name, rest = parts[0], parts[1]
    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Пайплайн **{pipeline_name}** не найден")
        return

    # Detect optional type keyword
    filter_type = "allow"
    words = rest.split(maxsplit=1)
    if words and words[0].lower() in ("allow", "block"):
        filter_type = words[0].lower()
        rest = words[1] if len(words) > 1 else ""

    parts2 = rest.split(maxsplit=1)
    if len(parts2) < 2:
        await event.respond(
            "Использование: `.add_filter <pipeline> [allow|block] <name> <выражение>`"
        )
        return

    name, expression = parts2[0], parts2[1]
    try:
        await service.add_filter(pipeline.id, name, expression, filter_type)
        icon = "🚫" if filter_type == "block" else "✅"
        await event.respond(f"{icon} Фильтр **{name}** добавлен в пайплайн **{pipeline_name}**")
    except SyntaxError as e:
        await event.respond(f"❌ Ошибка в выражении: {e}")
    except Exception as e:
        await event.respond(f"❌ {e}")


async def _cmd_remove_filter(event, args: str) -> None:
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await event.respond("Использование: `.remove_filter <pipeline> <name>`")
        return

    pipeline_name, filter_name = parts[0], parts[1].strip()
    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Пайплайн **{pipeline_name}** не найден")
        return

    removed = await service.remove_filter(pipeline.id, filter_name)
    if removed:
        await event.respond(f"✅ Фильтр **{filter_name}** удалён из пайплайна **{pipeline_name}**")
    else:
        await event.respond(f"⚠️ Фильтр **{filter_name}** не найден в пайплайне **{pipeline_name}**")


async def _cmd_list_filters(event, args: str) -> None:
    pipeline_name = args.strip()
    if not pipeline_name:
        await event.respond("Использование: `.list_filters <pipeline>`")
        return

    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Пайплайн **{pipeline_name}** не найден")
        return

    filters = await storage.get_filters_for_pipeline(pipeline.id)
    if not filters:
        await event.respond(f"В пайплайне **{pipeline_name}** нет фильтров. Добавьте: `.add_filter {pipeline_name} <name> <выражение>`")
        return

    lines = [f"**Фильтры пайплайна {pipeline_name}:**"]
    for f in filters:
        icon = "🚫" if f.type == "block" else "✅"
        lines.append(f"{icon} **{f.name}**: `{f.expression}`")
    await event.respond("\n".join(lines))


async def _cmd_test(event, args: str) -> None:
    # Optional: --from @username at the end
    author = ""
    if "--from" in args:
        idx = args.rfind("--from")
        from_str = args[idx + len("--from"):].strip().lstrip("@")
        args = args[:idx].strip()
        author = from_str

    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        await event.respond("Использование: `.test <pipeline> <filter_name> <текст> [--from @user]`")
        return

    pipeline_name, filter_name, text = parts[0], parts[1], parts[2]
    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Пайплайн **{pipeline_name}** не найден")
        return

    filters = await storage.get_filters_for_pipeline(pipeline.id)
    target = next((f for f in filters if f.name == filter_name), None)
    if target is None:
        await event.respond(f"❌ Фильтр **{filter_name}** не найден в пайплайне **{pipeline_name}**")
        return

    try:
        import expr_parser
        ast = expr_parser.parse(target.expression)
        result = expr_parser.evaluate(ast, text, author)
        icon = "✅" if result else "❌"
        type_label = "block" if target.type == "block" else "allow"
        author_note = f"\nАвтор: `@{author}`" if author else ""
        await event.respond(
            f"{icon} Фильтр **{filter_name}** [{type_label}] (`{target.expression}`)\n"
            f"Текст: _{text}_{author_note}\n"
            f"Результат: **{'совпадение' if result else 'нет совпадения'}**"
        )
    except Exception as e:
        await event.respond(f"❌ Ошибка: {e}")


async def _cmd_status(event, _args: str) -> None:
    pipelines = await storage.get_all_pipelines()
    if not pipelines:
        await event.respond("Пайплайны не созданы.")
        return
    lines = [f"**Статус userbot'а** ({len(pipelines)} пайплайн{'а' if 2 <= len(pipelines) <= 4 else 'ов' if len(pipelines) >= 5 else ''}):\n"]
    for p in pipelines:
        src = f"@{p.source_username}" if p.source_username else str(p.source_id)
        n_allow, n_block = await storage.count_filters_for_pipeline(p.id)
        if n_allow == 0 and n_block == 0:
            mode = "нет фильтров (проходит всё)"
        elif n_allow == 0:
            mode = f"pass-all + {n_block} block"
        else:
            mode = f"{n_allow} allow + {n_block} block"
        lines.append(f"• **{p.name}**: {p.source_title} ({src}) → `{p.output_id}`\n  {mode}")
    await event.respond("\n".join(lines))


async def _cmd_help(event, _args: str) -> None:
    await event.respond(_HELP)


_COMMANDS = {
    "add_pipeline": _cmd_add_pipeline,
    "remove_pipeline": _cmd_remove_pipeline,
    "list_pipelines": _cmd_list_pipelines,
    "add_filter": _cmd_add_filter,
    "remove_filter": _cmd_remove_filter,
    "list_filters": _cmd_list_filters,
    "test": _cmd_test,
    "status": _cmd_status,
    "help": _cmd_help,
}


async def _handle(event: events.NewMessage.Event) -> None:
    text = event.raw_text.strip()
    parts = text[1:].split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = _COMMANDS.get(cmd)
    if handler is None:
        return

    who = "self" if event.out else f"trusted:{event.sender_id}"
    log.info("Команда [%s] .%s %s", who, cmd, args[:80])
    try:
        await handler(event, args)
    except Exception as e:
        log.exception("Ошибка в обработке команды '%s'", cmd)
        await event.respond(f"❌ Внутренняя ошибка: {e}")


def _is_command_event(e) -> bool:
    if not (e.is_private and (e.raw_text or "").startswith(".")):
        return False
    if e.out:
        return True
    return bool(config.TRUSTED_USERS and e.sender_id in config.TRUSTED_USERS)


def register(client) -> None:
    client.add_event_handler(
        _handle,
        events.NewMessage(func=_is_command_event),
    )
