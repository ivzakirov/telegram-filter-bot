from __future__ import annotations
import logging
from telethon import events
import config
import service
import storage

log = logging.getLogger(__name__)

_HELP = """
**Userbot commands** (Saved Messages or DMs from a trusted account):

`.add_pipeline <name> <source> <output>` — create a pipeline
`.remove_pipeline <name>` — delete a pipeline and all its filters
`.list_pipelines` — list all pipelines

`.add_filter <pipeline> [allow|block] <name> <expression>` — add a filter
`.remove_filter <pipeline> <name>` — delete a filter
`.list_filters <pipeline>` — list filters for a pipeline
`.test <pipeline> <name> <text> [--from @user]` — test a filter

`.status` — summary
`.help` — this help

**Arguments:**
• `<source>` and `<output>` — @username or numeric chat_id
• `allow` (default) — forward if matched, no further filters checked
• `block` — block if matched, no further filters checked
Filters are checked **in order**, the first match determines the outcome.
If no filter matched — message passes (add `block *` last to block the rest).

**Expression syntax:**
`AND`, `OR`, `NOT`, parentheses `()`, phrases in `"quotes"`
Wildcards: `python*`, `*spam*`, `sale?`
Regex: `/pattern/` e.g. `/py(thon|3)/`
Author: `@username` — matches the message sender

Examples:
  `.add_pipeline jobs @js_jobs -1001234567890`
  `.add_filter jobs allow python python AND NOT vacancy`
  `.add_filter jobs block spam ad* OR @spambot`
""".strip()


async def _cmd_add_pipeline(event, args: str) -> None:
    parts = args.split()
    if len(parts) < 3:
        await event.respond(
            "Usage: `.add_pipeline <name> <source> <output>`\n"
            "Example: `.add_pipeline jobs @js_jobs -1001234567890`"
        )
        return
    name, source_identifier, output_identifier = parts[0], parts[1], parts[2]
    try:
        pipeline = await service.add_pipeline(event.client, name, source_identifier, output_identifier)
        src = f"@{pipeline.source_username}" if pipeline.source_username else str(pipeline.source_id)
        await event.respond(
            f"✅ Pipeline **{name}** created\n"
            f"• Source: {pipeline.source_title} ({src})\n"
            f"• Output: `{pipeline.output_id}`"
        )
    except Exception as e:
        await event.respond(f"❌ {e}")


async def _cmd_remove_pipeline(event, args: str) -> None:
    name = args.strip()
    if not name:
        await event.respond("Usage: `.remove_pipeline <name>`")
        return
    removed = await service.remove_pipeline(name)
    if removed:
        await event.respond(f"✅ Pipeline **{name}** deleted")
    else:
        await event.respond(f"⚠️ Pipeline **{name}** not found")


async def _cmd_list_pipelines(event, _args: str) -> None:
    pipelines = await storage.get_all_pipelines()
    if not pipelines:
        await event.respond("No pipelines created. Add one: `.add_pipeline <name> <source> <output>`")
        return
    lines = ["**Pipelines:**"]
    for p in pipelines:
        src = f"@{p.source_username}" if p.source_username else str(p.source_id)
        n_allow, n_block = await storage.count_filters_for_pipeline(p.id)
        filter_info = f"{n_allow}✅ {n_block}🚫" if (n_allow or n_block) else "no filters"
        lines.append(f"• **{p.name}**: {p.source_title} ({src}) → `{p.output_id}` [{filter_info}]")
    await event.respond("\n".join(lines))


async def _cmd_add_filter(event, args: str) -> None:
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await event.respond(
            "Usage: `.add_filter <pipeline> [allow|block] <name> <expression>`\n"
            "Example: `.add_filter jobs allow python python AND NOT vacancy`"
        )
        return

    pipeline_name, rest = parts[0], parts[1]
    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Pipeline **{pipeline_name}** not found")
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
            "Usage: `.add_filter <pipeline> [allow|block] <name> <expression>`"
        )
        return

    name, expression = parts2[0], parts2[1]
    try:
        await service.add_filter(pipeline.id, name, expression, filter_type)
        icon = "🚫" if filter_type == "block" else "✅"
        await event.respond(f"{icon} Filter **{name}** added to pipeline **{pipeline_name}**")
    except SyntaxError as e:
        await event.respond(f"❌ Expression error: {e}")
    except Exception as e:
        await event.respond(f"❌ {e}")


async def _cmd_remove_filter(event, args: str) -> None:
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await event.respond("Usage: `.remove_filter <pipeline> <name>`")
        return

    pipeline_name, filter_name = parts[0], parts[1].strip()
    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Pipeline **{pipeline_name}** not found")
        return

    removed = await service.remove_filter(pipeline.id, filter_name)
    if removed:
        await event.respond(f"✅ Filter **{filter_name}** deleted from pipeline **{pipeline_name}**")
    else:
        await event.respond(f"⚠️ Filter **{filter_name}** not found in pipeline **{pipeline_name}**")


async def _cmd_list_filters(event, args: str) -> None:
    pipeline_name = args.strip()
    if not pipeline_name:
        await event.respond("Usage: `.list_filters <pipeline>`")
        return

    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Pipeline **{pipeline_name}** not found")
        return

    filters = await storage.get_filters_for_pipeline(pipeline.id)
    if not filters:
        await event.respond(f"Pipeline **{pipeline_name}** has no filters. Add one: `.add_filter {pipeline_name} <name> <expression>`")
        return

    lines = [f"**Filters for pipeline {pipeline_name}:**"]
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
        await event.respond("Usage: `.test <pipeline> <filter_name> <text> [--from @user]`")
        return

    pipeline_name, filter_name, text = parts[0], parts[1], parts[2]
    pipeline = await storage.get_pipeline_by_name(pipeline_name)
    if pipeline is None:
        await event.respond(f"❌ Pipeline **{pipeline_name}** not found")
        return

    filters = await storage.get_filters_for_pipeline(pipeline.id)
    target = next((f for f in filters if f.name == filter_name), None)
    if target is None:
        await event.respond(f"❌ Filter **{filter_name}** not found in pipeline **{pipeline_name}**")
        return

    try:
        import expr_parser
        ast = expr_parser.parse(target.expression)
        result = expr_parser.evaluate(ast, text, author)
        icon = "✅" if result else "❌"
        type_label = "block" if target.type == "block" else "allow"
        author_note = f"\nAuthor: `@{author}`" if author else ""
        await event.respond(
            f"{icon} Filter **{filter_name}** [{type_label}] (`{target.expression}`)\n"
            f"Text: _{text}_{author_note}\n"
            f"Result: **{'match' if result else 'no match'}**"
        )
    except Exception as e:
        await event.respond(f"❌ Error: {e}")


async def _cmd_status(event, _args: str) -> None:
    pipelines = await storage.get_all_pipelines()
    if not pipelines:
        await event.respond("No pipelines created.")
        return
    n = len(pipelines)
    lines = [f"**Userbot status** ({n} pipeline{'s' if n != 1 else ''}):\n"]
    for p in pipelines:
        src = f"@{p.source_username}" if p.source_username else str(p.source_id)
        n_allow, n_block = await storage.count_filters_for_pipeline(p.id)
        if n_allow == 0 and n_block == 0:
            mode = "no filters (pass-all)"
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
    log.info("Command [%s] .%s %s", who, cmd, args[:80])
    try:
        await handler(event, args)
    except Exception as e:
        log.exception("Error handling command '%s'", cmd)
        await event.respond(f"❌ Internal error: {e}")


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
