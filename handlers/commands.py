from __future__ import annotations
import logging
from telethon import events
import service
import storage

log = logging.getLogger(__name__)

_HELP = """
**Команды userbot'а** (отправлять в Saved Messages):

`.add_chat @username|chat_id` — добавить канал/группу в мониторинг
`.remove_chat @username|chat_id` — убрать из мониторинга
`.list_chats` — список отслеживаемых чатов

`.add_filter <имя> <выражение>` — добавить глобальный фильтр
`.add_filter <имя> <выражение> --chat @username` — фильтр для конкретного чата
`.remove_filter <имя>` — удалить фильтр
`.list_filters` — список всех фильтров
`.test <имя> <текст>` — проверить фильтр на тексте

`.status` — сводка
`.help` — эта справка

**Синтаксис выражений:**
`AND`, `OR`, `NOT`, скобки `()`, фразы в `"кавычках"`

Примеры:
  `.add_filter news python AND (flask OR django) AND NOT вакансия`
  `.add_filter crypto (bitcoin OR ethereum) AND NOT реклама`
""".strip()


async def _cmd_add_chat(event, args: str) -> None:
    identifier = args.strip()
    if not identifier:
        await event.respond("Использование: `.add_chat @username` или `.add_chat chat_id`")
        return
    try:
        chat = await service.add_chat(event.client, identifier)
        await event.respond(f"✅ Добавлен: **{chat.title}** (id: `{chat.chat_id}`)")
    except Exception as e:
        await event.respond(f"❌ {e}")


async def _cmd_remove_chat(event, args: str) -> None:
    identifier = args.strip()
    if not identifier:
        await event.respond("Использование: `.remove_chat @username` или `.remove_chat chat_id`")
        return
    try:
        removed = await service.remove_chat(event.client, identifier)
        if removed:
            await event.respond("✅ Чат удалён из мониторинга")
        else:
            await event.respond("⚠️ Чат не найден в списке мониторинга")
    except Exception as e:
        await event.respond(f"❌ {e}")


async def _cmd_list_chats(event, _args: str) -> None:
    chats = await storage.get_all_chats()
    if not chats:
        await event.respond("Список мониторинга пуст. Добавьте чат: `.add_chat @username`")
        return
    lines = ["**Отслеживаемые чаты:**"]
    for c in chats:
        mention = f"@{c.username}" if c.username else f"`{c.chat_id}`"
        lines.append(f"• {c.title} ({mention})")
    await event.respond("\n".join(lines))


async def _cmd_add_filter(event, args: str) -> None:
    chat_id = None

    if "--chat" in args:
        idx = args.rfind("--chat")
        chat_str = args[idx + len("--chat"):].strip()
        args = args[:idx].strip()
        if not chat_str:
            await event.respond("❌ После `--chat` укажите username или chat_id")
            return
        try:
            from telethon.utils import get_peer_id
            entity = await event.client.get_entity(chat_str)
            chat_id = get_peer_id(entity)
        except Exception as e:
            await event.respond(f"❌ Не удалось найти чат: {e}")
            return

    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await event.respond(
            "Использование: `.add_filter <имя> <выражение>`\n"
            "Пример: `.add_filter news python AND NOT вакансия`"
        )
        return

    name, expression = parts[0], parts[1]
    try:
        await service.add_filter(name, expression, chat_id)
        scope = f" для чата `{chat_id}`" if chat_id else " (глобальный)"
        await event.respond(f"✅ Фильтр **{name}** добавлен{scope}")
    except SyntaxError as e:
        await event.respond(f"❌ Ошибка в выражении: {e}")
    except Exception as e:
        await event.respond(f"❌ {e}")


async def _cmd_remove_filter(event, args: str) -> None:
    name = args.strip()
    if not name:
        await event.respond("Использование: `.remove_filter <имя>`")
        return
    removed = await service.remove_filter(name)
    if removed:
        await event.respond(f"✅ Фильтр **{name}** удалён")
    else:
        await event.respond(f"⚠️ Фильтр **{name}** не найден")


async def _cmd_list_filters(event, _args: str) -> None:
    fltrs = await storage.get_all_filters()
    if not fltrs:
        await event.respond("Фильтры не заданы. Добавьте: `.add_filter <имя> <выражение>`")
        return
    lines = ["**Фильтры:**"]
    for f in fltrs:
        scope = f" [chat {f.chat_id}]" if f.chat_id else " [глобальный]"
        lines.append(f"• **{f.name}**{scope}: `{f.expression}`")
    await event.respond("\n".join(lines))


async def _cmd_test(event, args: str) -> None:
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await event.respond("Использование: `.test <имя_фильтра> <текст>`")
        return

    name, text = parts[0], parts[1]
    fltrs = await storage.get_all_filters()
    target = next((f for f in fltrs if f.name == name), None)
    if target is None:
        await event.respond(f"❌ Фильтр **{name}** не найден")
        return

    try:
        import expr_parser
        ast = expr_parser.parse(target.expression)
        result = expr_parser.evaluate(ast, text)
        icon = "✅" if result else "❌"
        await event.respond(
            f"{icon} Фильтр **{name}** (`{target.expression}`)\n"
            f"Текст: _{text}_\n"
            f"Результат: **{'совпадение' if result else 'нет совпадения'}**"
        )
    except Exception as e:
        await event.respond(f"❌ Ошибка: {e}")


async def _cmd_status(event, _args: str) -> None:
    n_chats = await storage.count_chats()
    n_filters = await storage.count_filters()
    await event.respond(
        f"**Статус userbot'а:**\n"
        f"• Чатов в мониторинге: {n_chats}\n"
        f"• Фильтров: {n_filters}"
    )


async def _cmd_help(event, _args: str) -> None:
    await event.respond(_HELP)


_COMMANDS = {
    "add_chat": _cmd_add_chat,
    "remove_chat": _cmd_remove_chat,
    "list_chats": _cmd_list_chats,
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

    try:
        await handler(event, args)
    except Exception as e:
        log.exception("Ошибка в обработке команды '%s'", cmd)
        await event.respond(f"❌ Внутренняя ошибка: {e}")


def register(client) -> None:
    client.add_event_handler(
        _handle,
        events.NewMessage(
            outgoing=True,
            func=lambda e: e.is_private and (e.raw_text or "").startswith("."),
        ),
    )
