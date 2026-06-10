"""
yt-dlp 下载器（最终兜底）

只做信息提取（skip_download=True），将真实直链交给 download_file 处理，
避免 yt-dlp 自己控制文件名与路径。
"""
import logging
import os
from typing import List, Optional

import config
from .base import BaseDownloader, MediaItem

logger = logging.getLogger(__name__)


class YtDlpDownloader(BaseDownloader):
    """
    使用 yt-dlp 提取推文媒体直链，作为最终备用方案。
    仅提取信息，不执行实际下载（由统一的 download_file 负责）。
    """
    name = "yt-dlp"

    def __init__(self, cookies_file: Optional[str] = None) -> None:
        self.cookies_file = cookies_file

    def get_media(self, tweet_url: str) -> List[MediaItem]:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            logger.warning(
                "[yt-dlp] 未安装，跳过。安装命令: pip install yt-dlp"
            )
            return []

        import yt_dlp

        ydl_opts: dict = {
            "quiet": not config.DEBUG_MODE,
            "no_warnings": not config.DEBUG_MODE,
            "skip_download": True,
            "extract_flat": False,
            "noplaylist": False,
        }

        if self.cookies_file and os.path.isfile(self.cookies_file):
            ydl_opts["cookiefile"] = self.cookies_file
            logger.info(f"[yt-dlp] 使用 cookies 文件: {self.cookies_file}")

        proxy = config.HTTP_PROXY or config.HTTPS_PROXY
        if proxy:
            ydl_opts["proxy"] = proxy

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(tweet_url, download=False)
                if not info:
                    return []
                return self._parse_info(info)
        except Exception as exc:
            logger.warning(f"[yt-dlp] 信息提取失败: {exc}")
            return []

    # ── 解析 ──────────────────────────────────

    def _parse_info(self, info: dict) -> List[MediaItem]:
        tweet_text = info.get("description", "")
        tweet_author = info.get("uploader_id") or info.get("uploader", "")

        # 多媒体推文（playlist 型）
        entries = info.get("entries") or []
        if entries:
            items: List[MediaItem] = []
            for entry in entries:
                if entry:
                    items.extend(self._single_item(entry, tweet_text, tweet_author))
            return items

        return self._single_item(info, tweet_text, tweet_author)

    def _single_item(
        self, info: dict, tweet_text: str, tweet_author: str
    ) -> List[MediaItem]:
        formats = info.get("formats", [])
        ext = (info.get("ext") or "").lower()
        thumbnail = info.get("thumbnail")
        duration = info.get("duration")
        width = info.get("width")
        height = info.get("height")

        # 判断媒体类型
        if ext in ("mp4", "mov", "webm", "mkv", "m3u8"):
            mtype = "video"
        elif ext == "gif":
            mtype = "gif"
        else:
            # 通过 vcodec 判断
            vcodec = info.get("vcodec", "none")
            mtype = "video" if vcodec and vcodec != "none" else "photo"

        # 对视频挑选最佳直链
        url = ""
        if mtype in ("video", "gif") and formats:
            url = self._best_video_url(formats) or ""
        if not url:
            url = info.get("url") or info.get("webpage_url", "")

        if not url:
            return []

        return [
            MediaItem(
                url=url,
                media_type=mtype,
                thumb_url=thumbnail,
                duration=int(duration) if duration else None,
                width=width,
                height=height,
                tweet_text=tweet_text,
                tweet_author=tweet_author,
            )
        ]

    def _best_video_url(self, formats: list) -> Optional[str]:
        """从 formats 中挑选最佳有视频流的 MP4 URL。"""
        def score(f: dict) -> float:
            if f.get("vcodec", "none") == "none":
                return -1
            return f.get("tbr") or (f.get("height") or 0) * 10 or 0

        candidates = [
            f for f in formats
            if f.get("url") and score(f) >= 0
        ]
        if not candidates:
            return None
        candidates.sort(key=score, reverse=True)
        return candidates[0]["url"]

