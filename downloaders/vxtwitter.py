"""
VxTwitter / FxTwitter API 下载器（首选）

端点格式:
  vxtwitter: https://api.vxtwitter.com/{username}/status/{tweet_id}
  fxtwitter:  https://api.fxtwitter.com/{username}/status/{tweet_id}
"""
import json
import logging
from typing import List, Optional

import requests

import config
from .base import BaseDownloader, MediaItem
from utils.helpers import extract_tweet_id, extract_username, get_proxies

logger = logging.getLogger(__name__)

_REQUEST_HEADERS = {
    "User-Agent": "TelegramBot/1.0 (compatible; TwitterMediaDownloader)",
    "Accept": "application/json",
}


# ──────────────────────────────────────────────
#  内部工具函数
# ──────────────────────────────────────────────

def _fetch_api(api_base: str, username: str, tweet_id: str) -> Optional[dict]:
    """请求 VX 类 API 并返回解析好的 JSON，失败返回 None。"""
    url = f"{api_base}/{username}/status/{tweet_id}"
    try:
        logger.info(f"请求 API: {url}")
        resp = requests.get(
            url,
            headers=_REQUEST_HEADERS,
            timeout=20,
            proxies=get_proxies(),
        )
        resp.raise_for_status()
        data = resp.json()
        if config.DEBUG_MODE:
            logger.debug(f"API 响应: {json.dumps(data, ensure_ascii=False)[:600]}")
        return data
    except Exception as exc:
        logger.warning(f"API 请求失败 [{url}]: {exc}")
        return None


def _best_video_url(variants: list) -> Optional[str]:
    """从 variants 列表中挑选比特率最高的 MP4 URL。"""
    mp4 = [
        v for v in variants
        if isinstance(v, dict)
        and v.get("content_type", "").lower() == "video/mp4"
        and v.get("url")
    ]
    if not mp4:
        # 兜底：取任意有 URL 的 variant
        mp4 = [v for v in variants if isinstance(v, dict) and v.get("url")]
    if not mp4:
        return None
    mp4.sort(key=lambda v: v.get("bitrate", 0), reverse=True)
    return mp4[0]["url"]


def _parse_media_extended(
    media_list: list,
    tweet_text: str = "",
    tweet_author: str = "",
) -> List[MediaItem]:
    """解析 vxtwitter 的 media_extended 字段。"""
    items: List[MediaItem] = []
    seen: set = set()

    for media in media_list:
        if not isinstance(media, dict):
            continue
        mtype = media.get("type", "image").lower()
        thumb = media.get("thumbnail_url") or media.get("thumbnail")

        if mtype == "video":
            variants = media.get("variants", [])
            url = _best_video_url(variants) or media.get("url", "")
            duration = media.get("duration")
            width = media.get("width")
            height = media.get("height")
            if url and url not in seen:
                seen.add(url)
                items.append(MediaItem(
                    url=url,
                    media_type="video",
                    thumb_url=thumb,
                    duration=int(duration) if duration else None,
                    width=width,
                    height=height,
                    tweet_text=tweet_text,
                    tweet_author=tweet_author,
                ))

        elif mtype in ("gif", "animated_gif"):
            url = media.get("url", "")
            if url and url not in seen:
                seen.add(url)
                items.append(MediaItem(
                    url=url,
                    media_type="gif",
                    thumb_url=thumb,
                    tweet_text=tweet_text,
                    tweet_author=tweet_author,
                ))

        else:  # image / photo
            url = media.get("url", "")
            if url and url not in seen:
                seen.add(url)
                items.append(MediaItem(
                    url=url,
                    media_type="photo",
                    tweet_text=tweet_text,
                    tweet_author=tweet_author,
                ))

    return items


def _parse_fxtwitter_media(
    media_obj: dict,
    tweet_text: str = "",
    tweet_author: str = "",
) -> List[MediaItem]:
    """
    解析 fxtwitter 的 tweet.media 字段。
    结构: {"all": [...], "photos": [...], "videos": [...]}
    """
    all_media = media_obj.get("all", [])
    if not all_media:
        all_media = media_obj.get("photos", []) + media_obj.get("videos", [])
    return _parse_media_extended(all_media, tweet_text, tweet_author)


def _fallback_mediaURLs(
    media_urls: list,
    tweet_text: str = "",
    tweet_author: str = "",
) -> List[MediaItem]:
    """从 mediaURLs 数组（无类型信息）中构建 MediaItem 列表。"""
    items: List[MediaItem] = []
    seen: set = set()
    for url in media_urls:
        if not url or url in seen:
            continue
        seen.add(url)
        path = url.lower().split("?")[0]
        if any(path.endswith(ext) for ext in (".mp4", ".mov", ".m3u8", ".webm")):
            mtype = "video"
        elif path.endswith(".gif"):
            mtype = "gif"
        else:
            mtype = "photo"
        items.append(MediaItem(
            url=url,
            media_type=mtype,
            tweet_text=tweet_text,
            tweet_author=tweet_author,
        ))
    return items


# ──────────────────────────────────────────────
#  下载器类
# ──────────────────────────────────────────────

class VxTwitterDownloader(BaseDownloader):
    """
    优先使用 vxtwitter.com API，失败后自动回退至 fxtwitter.com。
    两者均失败时返回空列表。
    """
    name = "vxtwitter"

    def get_media(self, tweet_url: str) -> List[MediaItem]:
        username = extract_username(tweet_url)
        tweet_id = extract_tweet_id(tweet_url)
        if not tweet_id:
            logger.error(f"[{self.name}] 无法从 URL 提取推文 ID: {tweet_url}")
            return []

        # 1. 尝试 vxtwitter
        data = _fetch_api(config.VXTWITTER_API_BASE, username, tweet_id)
        if data:
            items = self._parse_vxtwitter(data)
            if items:
                return items

        # 2. 回退至 fxtwitter
        logger.info(f"[{self.name}] vxtwitter 无结果，尝试 fxtwitter")
        data = _fetch_api(config.FXTWITTER_API_BASE, username, tweet_id)
        if data:
            items = self._parse_fxtwitter(data)
            if items:
                return items

        return []

    # ── 解析方法 ──────────────────────────────

    def _parse_vxtwitter(self, data: dict) -> List[MediaItem]:
        tweet_text = data.get("text", "")
        tweet_author = data.get("user_screen_name", "")

        # media_extended 包含完整类型信息
        media_extended = data.get("media_extended", [])
        if media_extended:
            items = _parse_media_extended(media_extended, tweet_text, tweet_author)
            if items:
                return items

        # 兜底：mediaURLs
        media_urls = data.get("mediaURLs", [])
        if media_urls:
            return _fallback_mediaURLs(media_urls, tweet_text, tweet_author)

        return []

    def _parse_fxtwitter(self, data: dict) -> List[MediaItem]:
        tweet_obj = data.get("tweet", {})
        tweet_text = tweet_obj.get("text", "")
        tweet_author = tweet_obj.get("author", {}).get("screen_name", "")

        media_obj = tweet_obj.get("media", {})
        if media_obj:
            items = _parse_fxtwitter_media(media_obj, tweet_text, tweet_author)
            if items:
                return items

        return []


