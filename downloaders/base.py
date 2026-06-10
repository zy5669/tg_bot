"""下载器基类与管理器"""
import re
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

_TWITTER_RE = re.compile(r"(?:twitter\.com|x\.com)/[^/\s]+/status/\d+")


@dataclass
class MediaItem:
    """单个媒体项目。"""
    url: str
    media_type: str          # "video" | "photo" | "gif"
    thumb_url: Optional[str] = None
    duration: Optional[int] = None   # 秒
    width: Optional[int] = None
    height: Optional[int] = None
    tweet_text: Optional[str] = None
    tweet_author: Optional[str] = None


class BaseDownloader:
    """下载器基类，子类必须重写 get_media。"""
    name: str = "base"

    def can_handle(self, url: str) -> bool:
        return bool(_TWITTER_RE.search(url))

    def get_media(self, tweet_url: str) -> List[MediaItem]:
        raise NotImplementedError


class DownloaderManager:
    """
    按注册顺序依次尝试各下载器，返回第一个成功的结果。
    """

    def __init__(self) -> None:
        self._downloaders: List[BaseDownloader] = []

    def register(self, downloader: BaseDownloader) -> None:
        self._downloaders.append(downloader)
        logger.debug(f"已注册下载器: {downloader.name}")

    def get_media(self, tweet_url: str) -> List[MediaItem]:
        for dl in self._downloaders:
            if not dl.can_handle(tweet_url):
                continue
            try:
                logger.info(f"[{dl.name}] 尝试获取媒体...")
                items = dl.get_media(tweet_url)
                if items:
                    logger.info(f"[{dl.name}] 成功获取 {len(items)} 个媒体项")
                    return items
                logger.info(f"[{dl.name}] 未找到媒体，继续尝试下一个")
            except Exception as exc:
                logger.warning(f"[{dl.name}] 失败: {exc}，继续尝试下一个")
        logger.error("所有下载器均未能获取媒体")
        return []


