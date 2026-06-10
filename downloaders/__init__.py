"""下载器模块"""
from typing import Optional

from .base import BaseDownloader, DownloaderManager, MediaItem
from .vxtwitter import VxTwitterDownloader
from .twitsave import TwitSaveDownloader, TwitterXZDownloader
from .ytdlp import YtDlpDownloader

__all__ = [
    "BaseDownloader",
    "DownloaderManager",
    "MediaItem",
    "VxTwitterDownloader",
    "TwitSaveDownloader",
    "TwitterXZDownloader",
    "YtDlpDownloader",
    "create_default_manager",
]


def create_default_manager(cookies_file: Optional[str] = None) -> DownloaderManager:
    """
    创建并返回默认下载器管理器，按优先级注册全部解析器：
      1. VxTwitterDownloader  — vxtwitter.com / fxtwitter.com API（最快）
      2. TwitSaveDownloader   — twitsave.com（备用）
      3. TwitterXZDownloader  — ssstwitter.com（备用）
      4. YtDlpDownloader      — yt-dlp（最全面，稍慢）
    """
    manager = DownloaderManager()
    manager.register(VxTwitterDownloader())
    manager.register(TwitSaveDownloader())
    manager.register(TwitterXZDownloader())
    manager.register(YtDlpDownloader(cookies_file))
    return manager

