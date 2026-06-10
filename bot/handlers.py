"""
Telegram Bot 消息处理器

流程:
  用户发送 Twitter/X 链接
    → 发送"正在处理"状态消息
    → 获取媒体信息（线程池中同步执行）
    → 逐一下载到临时文件
    → 上传到 Telegram
    → 清理所有临时文件
    → 删除状态消息
"""
import asyncio
import logging
import os
import time
from typing import List, Optional, Tuple

from telegram import (
    Update,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import config
from downloaders import MediaItem, create_default_manager
from utils.helpers import (
    extract_twitter_url,
    is_twitter_url,
    download_file,
    cleanup_file,
)

logger = logging.getLogger(__name__)

# 模块级单例，避免每次请求都重新创建
_manager = create_default_manager(config.YTDLP_COOKIES_FILE)


# ──────────────────────────────────────────────
#  工具函数
# ──────────────────────────────────────────────

def _is_authorized(user_id: Optional[int], is_self_bot: bool = False) -> bool:
    if is_self_bot:
        return True
    if not config.ALLOWED_USERS:
        return True
    if user_id is None:
        return False
    return user_id in config.ALLOWED_USERS


def _build_caption(item: MediaItem) -> str:
    """把推文作者和正文拼成 Telegram 标题（最多 1024 字符）。"""
    parts: List[str] = []
    if item.tweet_author:
        parts.append(f"👤 @{item.tweet_author}")
    if item.tweet_text:
        text = item.tweet_text.strip()
        if len(text) > 800:
            text = text[:800] + "…"
        parts.append(text)
    caption = "\n".join(parts)
    return caption[:1024]


async def _safe_edit(msg: Message, text: str) -> None:
    """编辑消息，失败时静默忽略。"""
    try:
        await msg.edit_text(text)
    except Exception:
        pass


async def _safe_delete(msg: Message) -> None:
    """删除消息，失败时静默忽略。"""
    try:
        await msg.delete()
    except Exception:
        pass


async def _run_sync(func, *args):
    """在默认线程池中执行同步函数。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)


# ──────────────────────────────────────────────
#  命令处理器
# ──────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(config.MSG_WELCOME)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            config.MSG_HELP, parse_mode=ParseMode.MARKDOWN
        )


# ──────────────────────────────────────────────
#  主消息处理器
# ──────────────────────────────────────────────

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理含 Twitter/X 链接的用户消息。"""
    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    is_self_bot = bool(user and user.is_bot and user.id == context.bot.id)
    if not _is_authorized(user.id if user else None, is_self_bot=is_self_bot):
        await message.reply_text(config.MSG_NOT_AUTHORIZED)
        return

    text = message.text or message.caption or ""
    if not is_twitter_url(text):
        return

    tweet_url = extract_twitter_url(text)
    if not tweet_url:
        return

    user_label = (
        f"{user.id} ({user.username})"
        if user
        else f"chat:{update.effective_chat.id if update.effective_chat else 'unknown'}"
    )
    logger.info(f"用户 {user_label} 请求: {tweet_url}")
    status_msg = await message.reply_text(config.MSG_PROCESSING)

    try:
        await _process_tweet(update, context, tweet_url, status_msg)
    except Exception as exc:
        logger.error(f"处理推文时发生未预期的错误: {exc}", exc_info=True)
        await _safe_edit(status_msg, config.MSG_DOWNLOAD_FAILED)


# ──────────────────────────────────────────────
#  核心处理流程
# ──────────────────────────────────────────────

async def _process_tweet(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tweet_url: str,
    status_msg: Message,
) -> None:
    # 1. 获取媒体信息
    await _safe_edit(status_msg, config.MSG_FETCHING)
    media_items: List[MediaItem] = await _run_sync(_manager.get_media, tweet_url)

    if not media_items:
        await _safe_edit(status_msg, config.MSG_NO_MEDIA)
        return

    caption = _build_caption(media_items[0])

    # 2. 按类型分组
    gifs     = [m for m in media_items if m.media_type == "gif"]
    regulars = [m for m in media_items if m.media_type != "gif"]

    # 3. 处理普通媒体（图片 + 视频）
    if regulars:
        await _handle_regulars(update, context, regulars, caption, status_msg)

    # 4. 处理 GIF（每个单独发送）
    for idx, gif_item in enumerate(gifs):
        gif_caption = caption if (not regulars and idx == 0) else ""
        await _send_animation(update, context, gif_item, gif_caption, status_msg)

    # 5. 删除状态消息
    await _safe_delete(status_msg)


async def _handle_regulars(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    items: List[MediaItem],
    caption: str,
    status_msg: Message,
) -> None:
    """下载并发送普通媒体（1 个→单发，多个→媒体组）。"""
    if len(items) == 1:
        await _safe_edit(status_msg, config.MSG_DOWNLOADING)
        await _send_single(update, context, items[0], caption, status_msg)
    else:
        await _send_group(update, context, items[:10], caption, status_msg)


def _get_telegram_api_uploader(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data.get("telegram_api_uploader")


def _file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


async def _send_large_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    item: MediaItem,
    path: str,
    caption: str,
    status_msg: Optional[Message] = None,
) -> bool:
    """Send a file through MTProto when Bot API upload would be too small."""
    uploader = _get_telegram_api_uploader(context)
    chat = update.effective_chat
    message = update.effective_message
    size_mb = _file_size_mb(path)
    if not uploader or not chat:
        if message:
            await message.reply_text(
                f"{config.MSG_FILE_TOO_LARGE}\n"
                "未启用 Telegram API 上传，请配置 TELEGRAM_API_ID 和 TELEGRAM_API_HASH。"
            )
        return False

    can_upload, reason = uploader.can_upload(path)
    if not can_upload:
        if message:
            await message.reply_text(f"{config.MSG_FILE_TOO_LARGE}\n{reason}")
        return False

    logger.info(
        "检测到大文件，切换 Telegram API 上传: chat_id=%s size=%.2f MB type=%s",
        chat.id,
        size_mb,
        item.media_type,
    )
    last_progress_at = 0.0
    last_percent = -1

    def progress_callback(current: int, total: int) -> None:
        nonlocal last_progress_at, last_percent
        if not total:
            return
        percent = int(current * 100 / total)
        now = time.monotonic()
        if percent < 100 and now - last_progress_at < config.TELEGRAM_API_PROGRESS_INTERVAL:
            return
        last_percent = percent
        last_progress_at = now
        logger.info(
            "Telegram API 上传进度: chat_id=%s %s/%s (%s%%)",
            chat.id,
            current,
            total,
            percent,
        )
        if status_msg:
            asyncio.create_task(
                _safe_edit(
                    status_msg,
                    f"{config.MSG_UPLOADING}\n"
                    f"Telegram API: {percent}% ({current / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB)",
                )
            )

    try:
        await uploader.send_file(
            chat.id,
            path,
            caption=caption or None,
            force_document=False,
            supports_streaming=item.media_type == "video",
            progress_callback=progress_callback,
        )
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    return True


async def _send_downloaded_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    item: MediaItem,
    path: str,
    caption: str,
    status_msg: Optional[Message] = None,
) -> None:
    """Upload an already downloaded media file via Bot API or MTProto."""
    size_mb = _file_size_mb(path)
    if size_mb > config.MAX_FILE_SIZE_MB:
        await _send_large_file(update, context, item, path, caption, status_msg)
        return

    thumb_path: Optional[str] = None
    thumb_fh = None
    try:
        if item.media_type == "video" and item.thumb_url:
            try:
                thumb_path, _ = await _run_sync(download_file, item.thumb_url)
                if thumb_path:
                    thumb_fh = open(thumb_path, "rb")
            except Exception:
                logger.debug("视频封面下载失败", exc_info=True)

        with open(path, "rb") as fh:
            message = update.effective_message
            if not message:
                raise RuntimeError("当前 update 没有可回复的消息")
            if item.media_type == "video":
                await message.reply_video(
                    video=fh,
                    caption=caption or None,
                    thumbnail=thumb_fh,
                    supports_streaming=True,
                    duration=item.duration,
                    width=item.width,
                    height=item.height,
                    read_timeout=60,
                    write_timeout=300,
                    connect_timeout=30,
                )
            elif item.media_type == "gif":
                await message.reply_animation(
                    animation=fh,
                    caption=caption or None,
                    read_timeout=60,
                    write_timeout=300,
                )
            else:
                await message.reply_photo(
                    photo=fh,
                    caption=caption or None,
                    read_timeout=60,
                    write_timeout=300,
                )
    finally:
        if thumb_fh:
            thumb_fh.close()
        cleanup_file(thumb_path)


# ──────────────────────────────────────────────
#  上传：单个媒体
# ──────────────────────────────────────────────

async def _send_single(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    item: MediaItem,
    caption: str,
    status_msg: Optional[Message] = None,
) -> None:
    """下载单个媒体并上传。"""
    temp_path: Optional[str] = None
    try:
        temp_path, _ = await _run_sync(download_file, item.url)
        if not temp_path:
            if update.effective_message:
                await update.effective_message.reply_text(config.MSG_DOWNLOAD_FAILED)
            return

        await _send_downloaded_file(
            update,
            context,
            item,
            temp_path,
            caption,
            status_msg,
        )

    except TelegramError as exc:
        logger.error(f"上传失败: {exc}")
        if update.effective_message:
            await update.effective_message.reply_text(
                config.MSG_UPLOAD_ERROR.format(error=str(exc))
            )
    except RuntimeError as exc:
        logger.error(f"Telegram API 上传失败: {exc}")
        if update.effective_message:
            await update.effective_message.reply_text(
                config.MSG_UPLOAD_ERROR.format(error=str(exc))
            )
    finally:
        cleanup_file(temp_path)


async def _send_animation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    item: MediaItem,
    caption: str,
    status_msg: Optional[Message] = None,
) -> None:
    """下载 GIF 并以动图形式发送。"""
    temp_path: Optional[str] = None
    try:
        temp_path, _ = await _run_sync(download_file, item.url)
        if not temp_path:
            return

        await _send_downloaded_file(
            update,
            context,
            item,
            temp_path,
            caption,
            status_msg,
        )
    except TelegramError as exc:
        logger.error(f"GIF 上传失败: {exc}")
    except RuntimeError as exc:
        logger.error(f"Telegram API GIF 上传失败: {exc}")
    finally:
        cleanup_file(temp_path)


# ──────────────────────────────────────────────
#  上传：媒体组
# ──────────────────────────────────────────────

async def _send_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    items: List[MediaItem],
    caption: str,
    status_msg: Message,
) -> None:
    """下载多个媒体并以媒体组发送（最多 10 个）。"""
    temp_paths: List[str] = []
    file_handles: List = []
    downloaded: List[Tuple[MediaItem, str]] = []

    try:
        total = len(items)
        for idx, item in enumerate(items):
            await _safe_edit(
                status_msg,
                config.MSG_DOWNLOADING_N.format(current=idx + 1, total=total),
            )
            temp_path, _ = await _run_sync(download_file, item.url)
            if not temp_path:
                logger.warning(f"媒体 {idx + 1} 下载失败，已跳过")
                continue

            temp_paths.append(temp_path)
            downloaded.append((item, temp_path))

        if not downloaded:
            await _safe_edit(status_msg, config.MSG_NO_MEDIA)
            return

        # 只有 1 个有效文件时退化为单发
        if len(downloaded) == 1:
            await _safe_edit(status_msg, config.MSG_UPLOADING)
            await _send_downloaded_file(
                update,
                context,
                downloaded[0][0],
                downloaded[0][1],
                caption,
                status_msg,
            )
            return

        has_large_file = any(
            _file_size_mb(path) > config.MAX_FILE_SIZE_MB
            for _, path in downloaded
        )
        if has_large_file:
            await _safe_edit(status_msg, config.MSG_UPLOADING)
            for i, (item, temp_path) in enumerate(downloaded):
                await _send_downloaded_file(
                    update,
                    context,
                    item,
                    temp_path,
                    caption if i == 0 else "",
                    status_msg,
                )
            return

        await _safe_edit(status_msg, config.MSG_UPLOADING)

        # 构建媒体组（保持文件句柄开放直到发送完毕）
        media_group = []
        for i, (item, temp_path) in enumerate(downloaded):
            fh = open(temp_path, "rb")
            file_handles.append(fh)
            item_caption = caption if i == 0 else None
            if item.media_type == "video":
                media_group.append(
                    InputMediaVideo(
                        media=fh,
                        caption=item_caption,
                        supports_streaming=True,
                    )
                )
            else:  # photo
                media_group.append(
                    InputMediaPhoto(media=fh, caption=item_caption)
                )

        message = update.effective_message
        if not message:
            raise RuntimeError("当前 update 没有可回复的消息")

        await message.reply_media_group(
            media=media_group,
            read_timeout=120,
            write_timeout=300,
            connect_timeout=30,
        )

    except TelegramError as exc:
        logger.error(f"媒体组上传失败: {exc}")
        if update.effective_message:
            await update.effective_message.reply_text(
                config.MSG_UPLOAD_ERROR.format(error=str(exc))
            )
    except RuntimeError as exc:
        logger.error(f"Telegram API 媒体组上传失败: {exc}")
        if update.effective_message:
            await update.effective_message.reply_text(
                config.MSG_UPLOAD_ERROR.format(error=str(exc))
            )
    finally:
        for fh in file_handles:
            try:
                fh.close()
            except Exception:
                pass
        for path in temp_paths:
            cleanup_file(path)


