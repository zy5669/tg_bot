"""
机器人配置文件
将 .env.example 复制为 .env 并填写实际值，或直接修改此文件中的默认值。
"""
import os
from pathlib import Path

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).parent

# ==================== Telegram Bot 配置 ====================

# Bot Token（从 @BotFather 获取）
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Telegram API（my.telegram.org 获取），用于通过 MTProto 上传超过 Bot API
# 50 MB 限制的文件。未配置时，大文件会给出明确提示。
TELEGRAM_API_ID_RAW: str = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_ID: int | None = (
    int(TELEGRAM_API_ID_RAW) if TELEGRAM_API_ID_RAW.isdigit() else None
)
TELEGRAM_API_HASH: str | None = os.getenv("TELEGRAM_API_HASH", "").strip() or None
TELEGRAM_SESSION_NAME: str = os.getenv(
    "TELEGRAM_SESSION_NAME",
    str(BASE_DIR / "telegram_bot_api"),
)

# 允许使用的用户 ID 列表（空列表 = 允许所有用户）
_allowed_raw = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS: list[int] = [
    int(uid.strip()) for uid in _allowed_raw.split(",") if uid.strip().isdigit()
]

# ==================== 下载配置 ====================

TEMP_DIR: str = str(BASE_DIR / "temp")

# Telegram Bot API 上传限制（MB）
MAX_FILE_SIZE_MB: float = 50.0

# MTProto 上传保护上限（MB）。Telegram 当前支持更大的文件，但机器人部署端
# 通常更需要一个可控的本地磁盘/带宽保护阈值。
MAX_TELEGRAM_API_FILE_SIZE_MB: float = float(
    os.getenv("MAX_TELEGRAM_API_FILE_SIZE_MB", "2000")
)

# 调试模式：显示更多日志
DEBUG_MODE: bool = os.getenv("DEBUG", "false").lower() == "true"

# ==================== API 端点 ====================

VXTWITTER_API_BASE: str = "https://api.vxtwitter.com"
FXTWITTER_API_BASE: str = "https://api.fxtwitter.com"
TWITSAVE_BASE: str = "https://twitsave.com"
SSSTWITTER_BASE: str = "https://ssstwitter.com"

# yt-dlp cookies 文件路径（用于下载需要登录的内容，可为 None）
YTDLP_COOKIES_FILE: str | None = os.getenv("YTDLP_COOKIES_FILE", None)

# ==================== 代理配置 ====================

# HTTP/HTTPS 代理，格式: "http://127.0.0.1:7890"，不使用则为 None
HTTP_PROXY: str | None = os.getenv("HTTP_PROXY", None)
HTTPS_PROXY: str | None = os.getenv("HTTPS_PROXY", None)

# ==================== 日志配置 ====================

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ==================== 用户消息模板（中文）====================

MSG_WELCOME = (
    "👋 欢迎使用 Twitter/X 媒体下载机器人！\n\n"
    "📎 直接发送 Twitter 或 X.com 链接，我将自动下载并发送媒体文件。\n\n"
    "发送 /help 查看使用帮助。"
)

MSG_HELP = (
    "📖 *使用帮助*\n\n"
    "• 直接发送 Twitter 或 X.com 链接\n"
    "• 支持图片、视频、GIF\n"
    "• 支持多图推文（最多 10 个）\n\n"
    "*示例链接：*\n"
    "`https://twitter.com/username/status/123456789`\n"
    "`https://x.com/username/status/123456789`"
)

MSG_PROCESSING     = "⏳ 正在处理，请稍候..."
MSG_FETCHING       = "⏳ 正在获取媒体信息..."
MSG_DOWNLOADING    = "⏳ 正在下载媒体文件..."
MSG_DOWNLOADING_N  = "⏳ 正在下载 ({current}/{total})..."
MSG_UPLOADING      = "⏳ 正在上传到 Telegram..."
MSG_NO_MEDIA       = "❌ 未找到可下载的媒体内容。\n该推文可能不含媒体，或已被删除/设为私有。"
MSG_DOWNLOAD_FAILED = "❌ 下载失败，请稍后重试。"
MSG_FILE_TOO_LARGE = "⚠️ 文件超过 Telegram Bot API 50 MB 限制。"
MSG_NOT_AUTHORIZED = "⛔ 您没有使用此机器人的权限。"
MSG_UPLOAD_ERROR   = "❌ 上传失败：{error}"

