"""Telegram MTProto uploader for files larger than the Bot API limit."""
import logging
import os
from dataclasses import dataclass
from typing import Optional

import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramApiStatus:
    enabled: bool
    reason: str = ""


class TelegramApiUploader:
    """Optional Telethon-based uploader using the bot token as MTProto login."""

    def __init__(self) -> None:
        self._client = None
        self.status = self._build_status()

    @staticmethod
    def _build_status() -> TelegramApiStatus:
        if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
            return TelegramApiStatus(
                enabled=False,
                reason="未配置 TELEGRAM_API_ID / TELEGRAM_API_HASH",
            )
        try:
            import telethon  # noqa: F401
        except ImportError:
            return TelegramApiStatus(
                enabled=False,
                reason="未安装 telethon 依赖",
            )
        return TelegramApiStatus(enabled=True)

    async def start(self) -> None:
        if not self.status.enabled:
            logger.info("Telegram API 大文件上传未启用: %s", self.status.reason)
            return

        from telethon import TelegramClient

        self._client = TelegramClient(
            config.TELEGRAM_SESSION_NAME,
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH,
        )
        await self._client.start(bot_token=config.BOT_TOKEN)
        logger.info("Telegram API 大文件上传已启用")

    async def stop(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None

    def can_upload(self, path: str) -> tuple[bool, str]:
        if not self.status.enabled or not self._client:
            return False, self.status.reason or "Telegram API 客户端未启动"

        size_mb = os.path.getsize(path) / (1024 * 1024)
        if size_mb > config.MAX_TELEGRAM_API_FILE_SIZE_MB:
            return (
                False,
                f"文件超过 MTProto 上传保护上限 {config.MAX_TELEGRAM_API_FILE_SIZE_MB:.0f} MB",
            )
        return True, ""

    async def send_file(
        self,
        chat_id: int,
        path: str,
        *,
        caption: Optional[str] = None,
        force_document: bool = False,
        supports_streaming: bool = True,
    ) -> None:
        can_upload, reason = self.can_upload(path)
        if not can_upload:
            raise RuntimeError(reason)

        await self._client.send_file(
            chat_id,
            path,
            caption=caption,
            force_document=force_document,
            supports_streaming=supports_streaming,
        )


async def create_telegram_api_uploader() -> TelegramApiUploader:
    uploader = TelegramApiUploader()
    await uploader.start()
    return uploader
