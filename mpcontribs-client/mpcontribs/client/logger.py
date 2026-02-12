from io import StringIO
import logging
import os
import sys

from mpcontribs.client.settings import MPCC_SETTINGS


class LogFilter(logging.Filter):
    def __init__(self, level, *args, **kwargs):
        self.level = level
        super().__init__(*args, **kwargs)

    def filter(self, record):
        return record.levelno < self.level


class CustomLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        prefix = self.extra.get("prefix")
        return f"[{prefix}] {msg}" if prefix else msg, kwargs


def get_logger(name: str = "mpcontribs.client"):
    logger = logging.getLogger(name)
    process = os.environ.get("SUPERVISOR_PROCESS_NAME")
    group = os.environ.get("SUPERVISOR_GROUP_NAME")
    cfg = {"prefix": f"{group}/{process}"} if process and group else {}
    info_handler = logging.StreamHandler(sys.stdout)
    error_handler = logging.StreamHandler(sys.stderr)
    info_handler.addFilter(LogFilter(logging.WARNING))
    error_handler.setLevel(max(logging.DEBUG, logging.WARNING))
    logger.handlers = [info_handler, error_handler]
    logger.setLevel(MPCC_SETTINGS.CLIENT_LOG_LEVEL)
    return CustomLoggerAdapter(logger, cfg)


MPCC_LOGGER = get_logger()


class TqdmToLogger(StringIO):
    logger: logging.Logger = MPCC_LOGGER
    level: int = MPCC_SETTINGS.CLIENT_LOG_LEVEL
    buf: str = ""

    def __init__(
        self, logger: logging.Logger = MPCC_LOGGER, level: int | None = None
    ) -> None:
        super().__init__()
        self.logger = logger
        self.level = level or logging.INFO

    def write(self, buf: str) -> int:
        self.buf = buf.strip("\r\n\t ")
        return 1

    def flush(self) -> None:
        self.logger.log(self.level, self.buf)
