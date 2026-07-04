import logging
import re


class TelegramTokenMaskFilter(logging.Filter):
    TELEGRAM_BOT_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.TELEGRAM_BOT_TOKEN_RE.sub("bot***:***", record.msg)

        if record.args:
            record.args = tuple(
                self.TELEGRAM_BOT_TOKEN_RE.sub("bot***:***", arg)
                if isinstance(arg, str)
                else arg
                for arg in record.args
            )

        return True


class DropHttpxRequestInfoFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "httpx" and record.getMessage().startswith("HTTP Request:"):
            return False

        return True


def configure_logging() -> None:
    root_logger = logging.getLogger()
    token_filter = TelegramTokenMaskFilter()
    httpx_request_filter = DropHttpxRequestInfoFilter()

    for handler in root_logger.handlers:
        handler.addFilter(token_filter)
        handler.addFilter(httpx_request_filter)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    force=True,
)

configure_logging()

logger = logging.getLogger("wb_profit_bot")
