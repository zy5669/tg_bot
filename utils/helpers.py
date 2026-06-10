"""辅助工具函数"""
import os
import re
import time
import tempfile
import logging
import requests
from urllib.parse import urlparse
from typing import Optional, Tuple

import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  URL 解析工具
# ──────────────────────────────────────────────

def extract_tweet_id(url: str) -> Optional[str]:
    """从推文 URL 中提取数字 ID。"""
    match = re.search(r"status/(\d+)", url)
    return match.group(1) if match else None


def extract_username(url: str) -> str:
    """从推文 URL 中提取用户名（@handle），提取失败返回 'Twitter'。"""
    match = re.search(r"(?:twitter\.com|x\.com)/([^/?#]+)/status", url)
    return match.group(1) if match else "Twitter"


def extract_twitter_url(text: str) -> Optional[str]:
    """从任意文本中提取第一条 Twitter/X 链接。"""
    match = re.search(
        r"https?://(?:www\.)?(?:x\.com|twitter\.com)/\S+/status/\d+\S*", text
    )
    return match.group(0).rstrip(".,;)\"'") if match else None


def is_twitter_url(text: str) -> bool:
    """检查文本中是否包含 Twitter/X 推文链接（需含 status/数字）。"""
    return bool(
        re.search(r"(?:x\.com|twitter\.com)/[^/\s]+/status/\d+", text)
    )


# ──────────────────────────────────────────────
#  文件工具
# ──────────────────────────────────────────────

def get_file_extension(url: str, content_type: str = "") -> str:
    """根据 URL 路径和 Content-Type 推断文件扩展名。"""
    path = url.lower().split("?")[0]
    if path.endswith((".mp4", ".mov", ".m3u8")):
        return ".mp4"
    if path.endswith((".jpg", ".jpeg")):
        return ".jpg"
    if path.endswith(".png"):
        return ".png"
    if path.endswith(".gif"):
        return ".gif"
    if path.endswith(".webm"):
        return ".webm"
    ct = content_type.lower()
    if "video" in ct:
        return ".mp4"
    if "image/jpeg" in ct or "image/jpg" in ct:
        return ".jpg"
    if "image/png" in ct:
        return ".png"
    if "image/gif" in ct:
        return ".gif"
    return ".bin"


def get_proxies() -> dict:
    """返回 requests 兼容的代理字典。"""
    proxies: dict = {}
    if config.HTTP_PROXY:
        proxies["http"] = config.HTTP_PROXY
    if config.HTTPS_PROXY:
        proxies["https"] = config.HTTPS_PROXY
    elif config.HTTP_PROXY:
        proxies["https"] = config.HTTP_PROXY
    return proxies


def download_file(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    将远程文件下载到临时目录。

    Returns:
        (temp_path, file_name) 或 (None, None)
    """
    temp_path: Optional[str] = None
    try:
        # 推断文件名与扩展名
        parsed = urlparse(url)
        file_name = os.path.basename(parsed.path).split("?")[0]
        if not file_name or "." not in file_name:
            try:
                head = requests.head(url, timeout=10, proxies=get_proxies(), allow_redirects=True)
                content_type = head.headers.get("Content-Type", "")
            except Exception:
                content_type = ""
            ext = get_file_extension(url, content_type)
            file_name = f"media_{int(time.time())}{ext}"

        suffix = os.path.splitext(file_name)[1] or ".bin"
        os.makedirs(config.TEMP_DIR, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=config.TEMP_DIR)
        os.close(fd)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://twitter.com/",
            "Accept": "*/*",
        }

        logger.info(f"开始下载: {url}")
        resp = requests.get(
            url, headers=headers, stream=True, timeout=90, proxies=get_proxies()
        )
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 65536  # 64 KB

        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if config.DEBUG_MODE and total > 0 and downloaded % (2 * 1024 * 1024) < chunk_size:
                        logger.debug(f"下载进度: {downloaded / total * 100:.1f}%")

        size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        logger.info(f"下载完成: {temp_path} ({size_mb:.2f} MB)")
        return temp_path, file_name

    except Exception as exc:
        logger.error(f"下载失败 [{url}]: {exc}")
        # 清理不完整的临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        return None, None


def cleanup_file(path: Optional[str]) -> None:
    """安全删除临时文件，失败时仅记录日志。"""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.unlink(path)
            logger.debug(f"已删除临时文件: {path}")
    except Exception as exc:
        logger.warning(f"删除临时文件失败 [{path}]: {exc}")


def format_file_size(size_bytes: int) -> str:
    """将字节数格式化为可读字符串。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 ** 2:.1f} MB"

