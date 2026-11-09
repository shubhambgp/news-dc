import logging
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

# Set per HTTP request by app.main.request_context; added to every log line of that request.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        rid = request_id_var.get()
        if rid and not hasattr(record, "request_id"):
            record.request_id = rid
        return True


def setup_logging(level: str = "INFO") -> None:
    """Route all logs (including uvicorn's) through one JSON handler on stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", timestamp=True)
    )
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # One line per outbound request drowns the ingest logs; failures are logged by the caller.
    for name in ("httpx", "httpx2"):  # httpx2 is the Anthropic SDK's HTTP client
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    # app.access logs every request with its request ID; uvicorn's own line would duplicate it.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
