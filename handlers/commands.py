from __future__ import annotations
import logging
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
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
`.remove_filter <имя>` — удалить фильтр (все варианты с этим именем)
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


async def _reply(client: Client, message, text: str) -> None:
    await client.send_message(message.chat.id, text)


async def _cmd_add_chat(client: Client, message, args: str) -> None:
    identifier = args.strip()
    if not identifier:
        await _reply(client, message, "Использование: `.add_chat @username` или `.add_chat chat_id`")
        return
    try:
        chat = await service.add_chat(client, identifier)
        await _reply(client, message, f"✅ Добавлен: **{chat.title}** (id: `{chat.chat_id}`)")
    except Exception as e:
        await _reply(client, message, f"❌ {e}")


async def _cmd_remove_chat(client: Client, message, args: str) -> None:
    identifier = args.strip()
    if not identifier:
        await _reply(client, message, "Использование: `.remove_chat @username` или `.remove_chat chat_id`")
        return
    try:
        removed = await service.remove_chat(client, identifier)
        if removed:
            await _reply(client, message, f"✅ Чат удалён из мониторинга")
        else:
            await _reply(client, message, "⚠️ Чат не найден в списке мониторинга")
    except Exception as e:
        await _reply(client, message, f"❌ {e}")


async def _cmd_list_chats(client: Client, message, _args: str) -> None:
    chats = await storage.get_all_chats()
    if not chats:
        await _reply(client, message, "Список мониторинга пуст. Добавьте чат: `.add_chat @username`")
        return
    lines = ["**Отслеживаемые чаты:**"]
    for c in chats:
        mention = f"@{c.username}" if c.username else f"`{c.chat_id}`"
        lines.append(f"• {c.title} ({mention})")
    await _reply(client, message, "\n".join(lines))


async def _cmd_add_filter(client: Client, message, args: str) -> None:
    chat_id = None

    if "--chat" in args:
        idx = args.rfind("--chat")
        chat_str = args[idx + len("--chat"):].strip()
        args = args[:idx].strip()
        if not chat_str:
            await _reply(client, message, "❌ После `--chat` укажите username или chat_id")
            return
        try:
            chat = await client.get_chat(chat_str)
            chat_id = chat.id
        except Exception as e:
            await _reply(client, message, f"❌ Не удалось найти чат: {e}")
            return

    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(
            client, message,
            "Использование: `.add_filter <имя> <выражение>`\n"
            "Пример: `.add_filter news python AND NOT вакансия`"
        )
        return

    name, expression = parts[0], parts[1]
    try:
        await service.add_filter(name, expression, chat_id)
        scope = f" для чата `{chat_id}`" if chat_id else " (глобальный)"
        await _reply(client, message, f"✅ Фильтр **{name}** добавлен{scope}")
    except SyntaxError as e:
        await _reply(client, message, f"❌ Ошибка в выражении: {e}")
    except Exception as e:
        await _reply(client, message, f"❌ {e}")


async def _cmd_remove_filter(client: Client, message, args: str) -> None:
    name = args.strip()
    if not name:
        await _reply(client, message, "Использование: `.remove_filter <имя>`")
        return
    removed = await service.remove_filter(name)
    if removed:
        await _reply(client, message, f"✅ Фильтр **{name}** удалён")
    else:
        await _reply(client, message, f"⚠️ Фильтр **{name}** не найден")


async def _cmd_list_filters(client: Client, message, _args: str) -> None:
    fltrs = await storage.get_all_filters()
    if not fltrs:
        await _reply(client, message, "Фильтры не заданы. Добавьте: `.add_filter <имя> <выражение>`")
        return
    lines = ["**Фильтры:**"]
    for f in fltrs:
        scope = f" [chat {f.chat_id}]" if f.chat_id else " [глобальный]"
        lines.append(f"• **{f.name}**{scope}: `{f.expression}`")
    await _reply(client, message, "\n".join(lines))


async def _cmd_test(client: Client, message, args: str) -> None:
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await _reply(client, message, "Использование: `.test <имя_фильтра> <текст>`")
        return

    name, text = parts[0], parts[1]
    fltrs = await storage.get_all_filters()
    target = next((f for f in fltrs if f.name == name), None)
    if target is None:
        await _reply(client, message, f"❌ Фильтр **{name}** не найден")
        return

    try:
        import expr_parser
        ast = expr_parser.parse(target.expression)
        result = expr_parser.evaluate(ast, text)
        icon = "✅" if result else "❌"
        await _reply(
            client, message,
            f"{icon} Фильтр **{name}** (`{target.expression}`)\n"
            f"Текст: _{text}_\n"
            f"Результат: **{'совпадение' if result else 'нет совпадения'}**"
        )
    except Exception as e:
        await _reply(client, message, f"❌ Ошибка: {e}")


async def _cmd_status(client: Client, message, _args: str) -> None:
    n_chats = await storage.count_chats()
    n_filters = await storage.count_filters()
    await _reply(
        client, message,
        f"**Статус userbot'а:**\n"
        f"• Чатов в мониторинге: {n_chats}\n"
        f"• Фильтров: {n_filters}"
    )


async def _cmd_help(client: Client, message, _args: str) -> None:
    await _reply(client, message, _HELP)


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


async def _handle(client: Client, message) -> None:
    text = (message.text or "").strip()
    if not text.startswith("."):
        return

    parts = text[1:].split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = _COMMANDS.get(cmd)
    if handler is None:
        return

    try:
        await handler(client, message, args)
    except Exception as e:
        log.exception("Ошибка в обработке команды '%s'", cmd)
        await _reply(client, message, f"❌ Внутренняя ошибка: {e}")


def register(app: Client) -> None:
    app.add_handler(
        MessageHandler(
            _handle,
            filters.me & filters.private & filters.regex(r"^\."),
        ),
        group=0,
    )
