"""
Twitter/X 媒体下载 Telegram 机器人
入口文件 — 运行: python main.py
"""
import logging
import os
import sys

from telegram.ext import Application, CommandHandler, MessageHandler, filters

import config
from bot.handlers import start_handler, help_handler, message_handler


def setup_logging() -> None:
    level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # 降低 httpx / httpcore 日志噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_application() -> Application:
    builder = Application.builder().token(config.BOT_TOKEN)

    # 若配置了代理，为 Telegram 连接也启用代理
    proxy = config.HTTP_PROXY or config.HTTPS_PROXY
    if proxy:
        from telegram.request import HTTPXRequest
        request = HTTPXRequest(proxy=proxy)
        builder = builder.request(request).get_updates_request(request)

    app = builder.build()

    # 注册命令处理器
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help",  help_handler))

    # 注册普通文本消息处理器（排除命令）
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
    )

    return app


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    if config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error(
            "请在 config.py 或 .env 文件中设置 BOT_TOKEN，然后重新运行。"
        )
        sys.exit(1)

    # 确保临时目录存在
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    logger.info(f"临时文件目录: {config.TEMP_DIR}")

    if config.HTTP_PROXY or config.HTTPS_PROXY:
        logger.info(f"代理: {config.HTTP_PROXY or config.HTTPS_PROXY}")

    logger.info("正在启动 Twitter 媒体下载机器人...")
    app = build_application()
    logger.info("机器人已就绪，按 Ctrl+C 停止。")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
