"""Central configuration loaded from .env (see .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
_channel_raw = os.getenv("CHANNEL_ID", "").strip()
try:
    CHANNEL_ID = int(_channel_raw) if _channel_raw else 0
except ValueError:
    CHANNEL_ID = 0

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
DISCORD_UPLOAD_LIMIT_MB = int(os.getenv("DISCORD_UPLOAD_LIMIT_MB", "8"))
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
MEDIA_TTL_HOURS = int(os.getenv("MEDIA_TTL_HOURS", "72"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
DATA_XLSX = os.path.join(BASE_DIR, "data", "media_log.xlsx")

MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
DISCORD_UPLOAD_LIMIT_BYTES = DISCORD_UPLOAD_LIMIT_MB * 1024 * 1024

# Only webcam-style media accepted for direct Discord posts.
ALLOWED_MIME_PREFIXES = ("image/", "video/")
