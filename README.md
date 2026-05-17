# telegram-filter-bot

A Telegram userbot that monitors source chats, applies sequential boolean filters, and forwards matching messages to output chats. Configured entirely via Telegram commands — no config files to edit at runtime.

## How it works

The core concept is a **pipeline**: a link from a source chat to an output chat, with an ordered list of filters evaluated against each incoming message.

Filters are checked in insertion order — the first match wins (like iptables rules):
- **allow** filter matches → message is forwarded
- **block** filter matches → message is dropped
- No filter matches → message passes through (add `block *` last to invert this)

## Features

- Boolean filter expressions: `AND`, `OR`, `NOT`, parentheses
- Quoted phrases: `"exact phrase"`
- Glob wildcards: `python*`, `*spam*`, `sale?`
- Regular expressions: `/py(thon|3)/`
- Author filtering: `@username`
- Media group (album) forwarding
- Reply chain preservation in output
- Catchup on startup and every 2 minutes: missed messages are backfilled from watermarks
- Multiple pipelines from the same source to different outputs
- Trusted account support: manage the bot from a second Telegram account via DMs

## Setup

**1. Get API credentials**

Go to [my.telegram.org](https://my.telegram.org), create an app, copy `API_ID` and `API_HASH`.

**2. Generate a session string**

```bash
python gen_session.py
```

Follow the prompts (phone number + confirmation code). Copy the printed string.

**3. Configure environment**

```bash
cp .env.example .env
```

Edit `.env`:

```env
API_ID=12345678
API_HASH=your_api_hash_here
SESSION_STRING=your_session_string_here

# Optional
DB_PATH=filters.db
TRUSTED_USERS=123456789,987654321
```

**4. Install dependencies**

```bash
python -m venv myvenv
myvenv/bin/pip install -r requirements.txt
```

**5. Run**

```bash
./start.sh
# or
myvenv/bin/python main.py
```

## Commands

Send commands to **Saved Messages** (or DMs from a trusted account). All commands start with `.`.

### Pipelines

```
.add_pipeline <name> <source> <output>
```
Create a pipeline. `<source>` and `<output>` accept `@username` or numeric `chat_id`.

```
.remove_pipeline <name>
```

```
.list_pipelines
```

### Filters

```
.add_filter <pipeline> [allow|block] <name> <expression>
```
`allow` is the default type if omitted.

```
.remove_filter <pipeline> <name>
```

```
.list_filters <pipeline>
```

```
.test <pipeline> <name> <text> [--from @user]
```
Test a single filter against a text without forwarding anything.

### Other

```
.status    — show all pipelines and their filter counts
.help      — show command reference
```

## Expression syntax

| Syntax | Example | Matches |
|--------|---------|---------|
| Plain word | `python` | any message containing "python" |
| AND | `python AND flask` | both words present |
| OR | `python OR java` | either word present |
| NOT | `NOT vacancy` | word absent |
| Parentheses | `(flask OR django) AND python` | grouped logic |
| Quoted phrase | `"new release"` | exact substring |
| Glob `*` | `*spam*` | any word containing "spam" |
| Glob `?` | `sale?` | "sales", "sale1", etc. |
| Regex | `/py(thon\|3)/` | regex match |
| Author | `@username` | message sent by that user |

Matching is case-insensitive. Expressions are Unicode-aware.

## Example setup

```
.add_pipeline jobs @dev_jobs -1001234567890
.add_filter jobs block ads ad* OR *promo* OR @spambot
.add_filter jobs allow python python AND NOT vacancy
.add_filter jobs block catchall *
```

Messages from `@dev_jobs` are evaluated in order:
1. Blocked if they look like ads
2. Forwarded if they mention Python but not job vacancies
3. Everything else is dropped

## Project structure

```
main.py            — entry point, keepalive loop
config.py          — env var loading
service.py         — pipeline/filter business logic
storage.py         — SQLite persistence (aiosqlite)
expr_parser.py     — boolean expression parser and evaluator
gen_session.py     — one-time session string generator
handlers/
  incoming.py      — real-time message handler, catchup, forwarding
  commands.py      — bot command handler
tests/
  test_expr_parser.py
```

## Running tests

```bash
myvenv/bin/python -m unittest tests/test_expr_parser.py -v
```
