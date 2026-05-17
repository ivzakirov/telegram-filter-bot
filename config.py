import os
from dotenv import load_dotenv

load_dotenv()

def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value

API_ID: int = int(_require("API_ID"))
API_HASH: str = _require("API_HASH")
SESSION_STRING: str = _require("SESSION_STRING")
DB_PATH: str = os.getenv("DB_PATH", "filters.db")

# Comma-separated Telegram user IDs allowed to send commands via DM
TRUSTED_USERS: set[int] = {
    int(x.strip())
    for x in os.getenv("TRUSTED_USERS", "").split(",")
    if x.strip().lstrip("-").isdigit()
}
