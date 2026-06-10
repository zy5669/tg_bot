"""
TwitSave / SSSTwitter 备用下载器

TwitSaveDownloader  — 请求 twitsave.com API / 解析 HTML
TwitterXZDownloader — 请求 ssstwitter.com（表单提交 + HTML 解析）
"""
import logging
import re
from typing import List

import requests
from bs4 import BeautifulSoup

import config
from .base import BaseDownloader, MediaItem
from utils.helpers import get_proxies

logger = logging.getLogger(__name__)

_COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ──────────────────────────────────────────────
#  TwitSaveDownloader
# ──────────────────────────────────────────────

class TwitSaveDownloader(BaseDownloader):
    """
    通过 twitsave.com 获取媒体直链。
    先尝试 JSON API，失败则解析 HTML 页面。
    """
    name = "twitsave"

    def get_media(self, tweet_url: str) -> List[MediaItem]:
        try:
            return self._try_api(tweet_url) or self._try_html(tweet_url)
        except Exception as exc:
            logger.warning(f"[{self.name}] 失败: {exc}")
            return []

    def _try_api(self, tweet_url: str) -> List[MediaItem]:
        """尝试 JSON 接口。"""
        try:
            resp = requests.get(
                f"{config.TWITSAVE_BASE}/info",
                params={"url": tweet_url},
                headers={**_COMMON_HEADERS, "Referer": config.TWITSAVE_BASE + "/"},
                timeout=20,
                proxies=get_proxies(),
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_json(data)
        except Exception as exc:
            logger.debug(f"[{self.name}] JSON API 失败: {exc}")
            return []

    def _try_html(self, tweet_url: str) -> List[MediaItem]:
        """解析 HTML 页面中的下载链接。"""
        try:
            resp = requests.get(
                config.TWITSAVE_BASE,
                params={"url": tweet_url},
                headers={**_COMMON_HEADERS, "Referer": "https://twitter.com/"},
                timeout=25,
                proxies=get_proxies(),
            )
            resp.raise_for_status()
            return self._parse_html(resp.text)
        except Exception as exc:
            logger.debug(f"[{self.name}] HTML 解析失败: {exc}")
            return []

    def _parse_json(self, data: dict) -> List[MediaItem]:
        items: List[MediaItem] = []
        # 尝试常见字段名
        for key in ("video", "videos", "media", "links"):
            for entry in data.get(key, []):
                url = entry.get("url") if isinstance(entry, dict) else entry
                if url and isinstance(url, str):
                    mtype = "video" if "video" in url.lower() or ".mp4" in url.lower() else "photo"
                    items.append(MediaItem(url=url, media_type=mtype))
        return items

    def _parse_html(self, html: str) -> List[MediaItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: List[MediaItem] = []
        seen: set = set()

        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            if "twimg.com" not in href and "pbs.twimg.com" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            low = href.lower()
            if any(ext in low for ext in (".mp4", ".m3u8", "video")):
                items.append(MediaItem(url=href, media_type="video"))
            else:
                items.append(MediaItem(url=href, media_type="photo"))

        return items


# ──────────────────────────────────────────────
#  TwitterXZDownloader（使用 ssstwitter.com）
# ──────────────────────────────────────────────

class TwitterXZDownloader(BaseDownloader):
    """
    通过 ssstwitter.com 表单提交获取媒体直链。
    """
    name = "ssstwitter"

    def get_media(self, tweet_url: str) -> List[MediaItem]:
        try:
            session = requests.Session()
            session.proxies.update(get_proxies())

            # 1. 获取首页 CSRF token
            home = session.get(
                config.SSSTWITTER_BASE,
                headers=_COMMON_HEADERS,
                timeout=15,
            )
            home.raise_for_status()
            token = self._extract_token(home.text)

            # 2. 提交下载请求
            post_headers = {
                **_COMMON_HEADERS,
                "Referer": config.SSSTWITTER_BASE + "/",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": config.SSSTWITTER_BASE,
            }
            payload: dict = {"id": tweet_url}
            if token:
                payload["_token"] = token

            resp = session.post(
                config.SSSTWITTER_BASE,
                data=payload,
                headers=post_headers,
                timeout=25,
            )
            resp.raise_for_status()
            return self._parse_response(resp.text)

        except Exception as exc:
            logger.warning(f"[{self.name}] 失败: {exc}")
            return []

    def _extract_token(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        inp = soup.find("input", {"name": "_token"})
        if inp and inp.get("value"):
            return inp["value"]
        # 备用：正则
        m = re.search(r'_token["\s:=]+([A-Za-z0-9+/=]{20,})', html)
        return m.group(1) if m else ""

    def _parse_response(self, html: str) -> List[MediaItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: List[MediaItem] = []
        seen: set = set()

        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            if href in seen:
                continue
            low = href.lower()
            if "twimg.com" in low or ".mp4" in low:
                seen.add(href)
                mtype = "video" if any(x in low for x in (".mp4", "video", "m3u8")) else "photo"
                items.append(MediaItem(url=href, media_type=mtype))

        return items



