"""Embedded HTTP endpoint for submitting tweet URLs from browser scripts."""
import logging
from types import SimpleNamespace
from typing import Any

from aiohttp import web
from telegram.ext import Application

import config
from bot.handlers import submit_tweet_url
from utils.helpers import extract_twitter_url, is_twitter_url

logger = logging.getLogger(__name__)


class HTTPSubmitServer:
    def __init__(self, app: Application) -> None:
        self.telegram_app = app
        self.web_app = web.Application(middlewares=[self._cors_middleware])
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

        self.web_app.router.add_get("/health", self.health)
        self.web_app.router.add_post("/submit", self.submit)
        self.web_app.router.add_options("/submit", self.options)

    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler):
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = config.HTTP_SUBMIT_CORS_ORIGIN
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Submit-Secret"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    async def start(self) -> None:
        if not config.HTTP_SUBMIT_ENABLED:
            logger.info("HTTP 提交服务未启用")
            return
        if not config.HTTP_SUBMIT_SECRET:
            logger.warning("HTTP 提交服务未启动: 缺少 HTTP_SUBMIT_SECRET")
            return

        self.runner = web.AppRunner(self.web_app)
        await self.runner.setup()
        self.site = web.TCPSite(
            self.runner,
            host=config.HTTP_SUBMIT_HOST,
            port=config.HTTP_SUBMIT_PORT,
        )
        await self.site.start()
        logger.info(
            "HTTP 提交服务已启动: http://%s:%s/submit",
            config.HTTP_SUBMIT_HOST,
            config.HTTP_SUBMIT_PORT,
        )

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            logger.info("HTTP 提交服务已停止")

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def options(self, request: web.Request) -> web.Response:
        return web.Response(status=204)

    async def submit(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return self._error("invalid_json", 400)

        if not self._is_authorized(request, payload):
            return self._error("unauthorized", 401)

        chat_id = self._parse_chat_id(payload.get("chat_id"))
        if chat_id is None:
            return self._error("invalid_chat_id", 400)

        text = str(payload.get("url") or payload.get("tweet_url") or "")
        if not is_twitter_url(text):
            return self._error("invalid_tweet_url", 400)

        tweet_url = extract_twitter_url(text)
        if not tweet_url:
            return self._error("invalid_tweet_url", 400)

        context = SimpleNamespace(
            application=self.telegram_app,
            bot=self.telegram_app.bot,
        )
        self.telegram_app.create_task(
            submit_tweet_url(context, chat_id, tweet_url),
            name=f"http-submit-{chat_id}",
        )
        logger.info("HTTP 提交已接收: chat_id=%s url=%s", chat_id, tweet_url)
        return web.json_response({"ok": True, "queued": True})

    @staticmethod
    def _parse_chat_id(value: Any) -> int | None:
        try:
            return int(str(value).strip())
        except Exception:
            return None

    @staticmethod
    def _is_authorized(request: web.Request, payload: dict) -> bool:
        expected = config.HTTP_SUBMIT_SECRET
        provided = (
            request.headers.get("X-Submit-Secret")
            or str(payload.get("secret") or "")
        )
        return bool(expected and provided and provided == expected)

    @staticmethod
    def _error(code: str, status: int) -> web.Response:
        return web.json_response({"ok": False, "error": code}, status=status)
