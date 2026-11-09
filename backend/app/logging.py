import logging

from pythonjsonlogger.json import JsonFormatter


def setup_logging(level: str = "INFO") -> None:
    """Route all logs (including uvicorn's) through one JSON handler on stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", timestamp=True)
    )
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
