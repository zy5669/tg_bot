"""Telegram MTProto uploader for files larger than the Bot API limit."""
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

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
        self._upload_semaphore = asyncio.Semaphore(
            config.TELEGRAM_API_CONCURRENT_UPLOADS
        )
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

        logger.info(
            "正在启动 Telegram API 大文件上传: api_id=%s session=%s concurrent_uploads=%s",
            config.TELEGRAM_API_ID,
            config.TELEGRAM_SESSION_NAME,
            config.TELEGRAM_API_CONCURRENT_UPLOADS,
        )
        self._client = TelegramClient(
            config.TELEGRAM_SESSION_NAME,
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH,
        )
        await self._client.start(bot_token=config.BOT_TOKEN)
        me = await self._client.get_me()
        username = f"@{me.username}" if getattr(me, "username", None) else me.id
        logger.info(
            "Telegram API 大文件上传已启用: bot=%s id=%s。"
            "使用 bot token 登录时不会出现手机号验证码。",
            username,
            me.id,
        )

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
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        can_upload, reason = self.can_upload(path)
        if not can_upload:
            raise RuntimeError(reason)

        size_mb = os.path.getsize(path) / (1024 * 1024)
        logger.info(
            "Telegram API 开始发送文件: chat_id=%s path=%s size=%.2f MB",
            chat_id,
            path,
            size_mb,
        )
        async with self._upload_semaphore:
            await self._client.send_file(
                chat_id,
                path,
                caption=caption,
                force_document=force_document,
                supports_streaming=supports_streaming,
                progress_callback=progress_callback,
            )
        logger.info(
            "Telegram API 文件发送完成: chat_id=%s path=%s size=%.2f MB",
            chat_id,
            path,
            size_mb,
        )


async def create_telegram_api_uploader() -> TelegramApiUploader:
    uploader = TelegramApiUploader()
    await uploader.start()
    return uploader
