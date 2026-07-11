import os

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


API_ID = os.getenv("API_ID", "your_api_id_here")  # Telegram App API ID
API_HASH = os.getenv("API_HASH", "your_api_hash_here")  # Telegram App API Hash
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")  # BotFather token
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny, base, small, medium, large
TTS_ENABLED = _get_bool("TTS_ENABLED", True)  # Enable/disable voice reply
