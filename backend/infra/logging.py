import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger


request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
project_id_ctx: ContextVar[str] = ContextVar("project_id", default="")
job_id_ctx: ContextVar[str] = ContextVar("job_id", default="")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("")
        record.project_id = project_id_ctx.get("")
        record.job_id = job_id_ctx.get("")
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(request_id)s %(project_id)s %(job_id)s %(message)s"
        )
    )
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers = []
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
